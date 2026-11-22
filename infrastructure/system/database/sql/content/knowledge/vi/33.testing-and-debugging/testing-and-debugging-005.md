# Kiểm thử Unicode, quy tắc đối chiếu và định danh có dấu

## 1. Vì sao dữ liệu Unicode cần được kiểm thử ở nhiều lớp?

Một ứng dụng có thể hiển thị đúng tên “Nguyễn Thị Ánh” trên màn hình nhưng vẫn gặp lỗi khi tìm kiếm, sắp xếp, tạo unique key hoặc kết nối dữ liệu giữa hai bảng.

Một số tình huống thường gặp:

- Người dùng nhập một chữ có dấu theo dạng Unicode dựng sẵn, trong khi dữ liệu cũ dùng ký tự nền và dấu kết hợp.
- Hai tên nhìn giống nhau nhưng có chuỗi code point khác nhau.
- Tìm kiếm không phân biệt hoa/thường ở một database nhưng lại phân biệt ở database khác.
- Một cột dùng collation không phân biệt dấu, khiến hai giá trị được coi là bằng nhau và xung đột unique constraint.
- Ký tự emoji bị cắt hoặc thay bằng ký tự lỗi do charset/driver không tương thích.
- Tên bảng hoặc cột có dấu chạy trên một hệ quản trị nhưng migration/tooling khác không xử lý giống nhau.
- Query sắp xếp tiếng Việt theo thứ tự không phù hợp với yêu cầu sản phẩm.

Các vấn đề này không chỉ nằm ở font chữ. Cần phân biệt **encoding**, **Unicode normalization**, **collation**, **cách ứng dụng bind dữ liệu** và **quy tắc định danh SQL**.

Bài học này tập trung vào cách kiểm thử và gỡ lỗi các vấn đề Unicode trong Database SQL, lấy Java/JDBC làm ví dụ ứng dụng và đối chiếu PostgreSQL, MySQL, SQL Server, Oracle, SQLite.

## 2. Năm khái niệm không nên đánh đồng

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Encoding/character set | Byte được giải mã thành ký tự như thế nào? | UTF-8, UTF-16 |
| Unicode normalization | Các chuỗi tương đương được biểu diễn thống nhất ra sao? | NFC, NFD |
| Collation | So sánh và sắp xếp chuỗi theo quy tắc nào? | Case-insensitive, accent-sensitive |
| Identifier rules | Tên bảng/cột được phân tích, quote và phân biệt thế nào? | CustomerName, "CustomerName" |
| Application mapping | Java, driver và DB truyền/nhận chuỗi ra sao? | String, setString, setNString |

Một cột có thể lưu UTF-8 hoàn toàn đúng nhưng vẫn tìm kiếm không như mong muốn do collation. Một collation có thể bỏ qua khác biệt dấu khi so sánh, nhưng không tự chuyển dữ liệu đã lưu từ NFD sang NFC. Quoting identifier có thể giúp parser hiểu tên cột có ký tự đặc biệt, nhưng không sửa lỗi encoding của giá trị dữ liệu.

**Khi gỡ lỗi, hãy xác định lớp nào đang sai trước khi thay đổi schema hoặc dữ liệu.**

## 3. Unicode: ký tự không đồng nghĩa với byte

Unicode gán mã cho các ký tự trong nhiều hệ chữ. Một **code point** được viết dạng U+....

Ví dụ:

| Ký tự | Code point |
| --- | --- |
| A | U+0041 |
| á | U+00E1 |
| đ | U+0111 |
| ắ | U+1EAF |
| 😀 | U+1F600 |

Code point không đồng nghĩa một byte. UTF-8 có thể dùng từ 1 đến 4 byte cho một code point; UTF-16 dùng một hoặc hai code unit 16-bit.

Một chuỗi hiển thị có thể gồm nhiều code point. Ví dụ chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc một chữ cái nền cộng dấu kết hợp.

### 3.1. Code point và grapheme cluster

Người dùng thường cảm nhận một ký tự hiển thị, hay **grapheme cluster**, trong khi máy tính có thể thấy nhiều code point.

Ví dụ chữ ắ có thể là:

- Một code point U+1EAF.
- Chữ a U+0061 + dấu breve U+0306 + dấu sắc U+0301.

Hai chuỗi có thể hiển thị giống nhau nhưng số code point và byte khác nhau.

Emoji cũng có thể là nhiều code point kết hợp qua variation selector, skin tone modifier hoặc zero-width joiner. Không nên đếm ký tự người dùng bằng cách đếm byte hoặc đơn vị UTF-16.

### 3.2. Độ dài phụ thuộc đơn vị đo

| Đơn vị | Đo điều gì? |
| --- | --- |
| Byte length | Dung lượng mã hóa |
| UTF-16 code unit | Đơn vị lưu trong Java String |
| Unicode code point | Mã Unicode |
| Grapheme cluster | Đơn vị gần với ký tự người dùng nhìn thấy |

Một giới hạn cột VARCHAR có thể được diễn giải theo ký tự hoặc byte tùy DBMS/kiểu dữ liệu/cấu hình. Không lấy String.length() trong Java để suy ra trực tiếp giới hạn cột ở mọi hệ quản trị.

## 4. Java String và UTF-16

Java String biểu diễn chuỗi theo UTF-16. Phương thức length() trả số code unit UTF-16, không phải số code point hay số ký tự người dùng nhìn thấy.

Ví dụ:

```java
String text = "A😀";

System.out.println(text.length()); // 3 UTF-16 code units
System.out.println(
    text.codePointCount(0, text.length())
); // 2 code points
```

Ký tự A dùng một code unit; emoji ngoài Basic Multilingual Plane dùng một surrogate pair gồm hai code unit.

### 4.1. Duyệt theo code point

```java
String text = "A😀";

for (int offset = 0; offset < text.length();) {
    int codePoint = text.codePointAt(offset);

    System.out.printf("U+%04X%n", codePoint);

    offset += Character.charCount(codePoint);
}
```

Không duyệt char rồi giả định mỗi char là một ký tự Unicode đầy đủ.

### 4.2. Đếm grapheme cluster

Nếu giao diện cần giới hạn số ký tự người dùng nhìn thấy, code point vẫn có thể chưa đủ. Một grapheme cluster có thể gồm nhiều code point.

Java có BreakIterator trong thư viện chuẩn; với yêu cầu Unicode segmentation mới và phức tạp, cần kiểm tra khả năng hỗ trợ phiên bản JDK hoặc thư viện ICU4J.

### 4.3. Không cắt chuỗi tùy tiện theo char index

```java
String clipped = text.substring(0, 2);
```

có thể cắt giữa surrogate pair hoặc giữa chữ và dấu kết hợp. Kết quả có thể thành chuỗi Unicode lỗi hoặc hiển thị không như mong đợi.

Nếu cần cắt theo giới hạn, phải xác định rõ giới hạn tính theo byte, code point hay grapheme cluster và đảm bảo không cắt giữa đơn vị mã hóa.

## 5. Unicode normalization: NFC, NFD, NFKC và NFKD

Unicode cho phép một số ký tự hiển thị giống nhau có nhiều cách biểu diễn.

- NFC thường ghép các chuỗi có thể ghép thành dạng dựng sẵn.
- NFD phân rã ký tự thành ký tự nền và dấu kết hợp.
- NFKC/NFKD còn áp dụng các phép tương đương tương thích, có thể thay đổi dạng ký tự rộng hơn.

### 5.1. Ví dụ tiếng Việt

Chữ ắ:

- Dạng dựng sẵn: U+1EAF.
- Dạng phân rã: U+0061 + U+0306 + U+0301.

Hai chuỗi có thể hiển thị giống nhau, nhưng phép so sánh nhị phân có thể coi chúng khác nhau.

### 5.2. Chuẩn hóa NFC trong Java

```java
import java.text.Normalizer;

String input = "a\u0306\u0301";

String normalized = Normalizer.normalize(
    input,
    Normalizer.Form.NFC
);
```

Sau chuẩn hóa NFC, chuỗi có thể được chuyển sang dạng dựng sẵn nếu Unicode định nghĩa phép ghép tương ứng.

### 5.3. Chuẩn hóa NFD

```java
String decomposed = Normalizer.normalize(
    "ắ",
    Normalizer.Form.NFD
);
```

NFD hữu ích cho một số phép phân tích hoặc tìm kiếm, nhưng không nên mặc định lưu mọi dữ liệu ở NFD. Chọn một dạng chuẩn thống nhất cho ứng dụng và kiểm thử driver/database có giữ nguyên dạng đó hay không.

### 5.4. NFKC/NFKD có thể thay đổi ý nghĩa

Các dạng compatibility có thể hợp nhất những ký tự nhìn gần giống hoặc được coi là tương đương về trình bày, ví dụ dạng full-width/half-width hoặc ký hiệu tương thích.

Không dùng NFKC như một bước “làm sạch mọi chuỗi” mà chưa xác định yêu cầu. Nó có thể làm mất khác biệt có ý nghĩa trong mã định danh, văn bản pháp lý hoặc nội dung người dùng.

### 5.5. Normalization không phải xóa dấu

NFC/NFD giải quyết cách biểu diễn tương đương theo Unicode. Chúng không tự biến ấ thành a, cũng không tự định nghĩa tìm kiếm không dấu.

Normalization và accent-insensitive comparison là hai việc khác nhau.

## 6. Tiếng Việt: dấu thanh, dấu phụ và chữ đ

Tiếng Việt dùng dấu thanh và dấu phụ trên nguyên âm. Chẳng hạn a, á, à, ả, ã, ạ, ă, â là những dạng khác nhau về nội dung.

Chữ đ/Đ cũng cần chú ý:

- đ là U+0111.
- d là U+0064.
- Đ là U+0110.
- D là U+0044.

đ không phải chữ d cộng một combining mark thông thường. Vì vậy một thuật toán chỉ loại bỏ combining marks sau NFD có thể không chuyển đ thành d.

### 6.1. “Tìm không dấu” là chính sách sản phẩm

Một sản phẩm có thể muốn truy vấn Nguyen khớp Nguyễn, nhưng điều đó không có nghĩa mọi cột tiếng Việt nên dùng collation bỏ dấu.

Cần quyết định theo từng chức năng:

- Tên hiển thị: giữ đúng dấu và dạng người dùng nhập.
- Đăng nhập/email: tuân theo quy tắc riêng của trường dữ liệu.
- Tìm kiếm tên: có thể hỗ trợ tìm không dấu nếu sản phẩm yêu cầu.
- Mã pháp lý hoặc tên chính thức: không tự xóa dấu khi so sánh định danh.
- Khóa duy nhất: phải xác định rõ hai cách viết nào được coi là trùng.

### 6.2. Không tự xóa mọi dấu để làm khóa

Một phép biến đổi kiểu:

```java
String key = Normalizer.normalize(
    name, Normalizer.Form.NFD
).replaceAll("\\p{M}+", "");
```

có thể bỏ dấu kết hợp, nhưng không xử lý đầy đủ chữ đ, không giải quyết locale/case folding và có thể gộp những tên khác nhau.

Nếu nghiệp vụ muốn bỏ dấu, hãy định nghĩa thuật toán riêng, test dữ liệu thực tế và giữ nguyên giá trị gốc.

### 6.3. Không dùng tìm kiếm không dấu làm xác thực danh tính

Hai tên gần giống hoặc không dấu không chứng minh cùng một người. Tìm kiếm tiện dụng không thay thế khóa định danh, email đã xác thực hoặc quy trình xác minh.

## 7. Encoding: UTF-8, UTF-16 và khả năng lưu dữ liệu

Encoding quy định cách chuyển chuỗi Unicode thành byte.

UTF-8 phổ biến cho web, file, API và nhiều database. UTF-16 thường gặp trong môi trường Java và một số kiểu dữ liệu database. Một DBMS có thể dùng encoding nội bộ khác với encoding của client.

### 7.1. Chuỗi đi qua nhiều chặng

```text
Trình duyệt / client
       |
       v
HTTP request (charset)
       |
       v
Java String
       |
       v
JDBC driver
       |
       v
Database connection encoding
       |
       v
Cột dữ liệu / storage
       |
       v
ResultSet / driver
       |
       v
Java String / HTTP response
```

Lỗi ở bất kỳ chặng nào đều có thể tạo ký tự mojibake, dấu hỏi hoặc ký tự thay thế.

### 7.2. UTF-8 trong file và HTTP

Khi đọc/ghi file, chỉ định charset rõ ràng:

```java
Files.writeString(
    path,
    text,
    StandardCharsets.UTF_8
);

String restored = Files.readString(
    path,
    StandardCharsets.UTF_8
);
```

Đối với HTTP, client và server cần thống nhất charset; với JSON hiện đại, nội dung được trao đổi theo Unicode và thường mã hóa UTF-8. Không dựa vào charset mặc định của máy.

### 7.3. Không sửa mojibake bằng cách đổi collation

Nếu byte UTF-8 đã bị giải mã nhầm thành ký tự sai rồi lưu vào database, đổi collation không khôi phục nội dung gốc. Cần xác định encoding ban đầu, nguồn dữ liệu và kế hoạch sửa dữ liệu có kiểm soát.

## 8. Collation là gì?

Collation là tập quy tắc để so sánh và sắp xếp chuỗi. Tùy DBMS/collation, các khác biệt có thể được xem là quan trọng hoặc bị bỏ qua:

- Hoa/thường: A so với a.
- Dấu: a so với á.
- Dạng Unicode dựng sẵn và phân rã.
- Độ rộng ký tự: full-width/half-width.
- Kana trong tiếng Nhật.
- Quy tắc ngôn ngữ và thứ tự chữ cái.
- Khoảng trắng cuối chuỗi.
- Ký tự có trọng số bằng nhau hoặc không có trọng số.

### 8.1. Case-sensitive và case-insensitive

- **CS:** phân biệt hoa/thường.
- **CI:** không phân biệt hoa/thường theo quy tắc collation.

Ví dụ với CI, AN và an có thể được coi là bằng nhau.

### 8.2. Accent-sensitive và accent-insensitive

- **AS:** phân biệt dấu.
- **AI:** không phân biệt dấu theo quy tắc collation.

Một collation AI có thể coi a và á là bằng nhau trong phép so sánh, nhưng hành vi cụ thể phụ thuộc locale/DBMS.

### 8.3. Collation không nhất thiết thay đổi dữ liệu lưu

Một cột có thể lưu nguyên văn Nguyễn và NGUYỄN, nhưng collation CI có thể coi chúng tương đương khi so sánh. Giá trị gốc vẫn là chuỗi được lưu.

### 8.4. Collation có thể ảnh hưởng unique constraint

Nếu unique index dùng collation không phân biệt hoa/thường hoặc dấu, hai chuỗi khác byte có thể bị coi là trùng.

Trước khi đổi collation hoặc tạo unique index, phải tìm các giá trị sẽ va chạm.

## 9. So sánh nhị phân và so sánh ngôn ngữ

Một collation nhị phân thường so sánh theo biểu diễn mã hóa hoặc mã ký tự theo quy tắc DBMS. Collation ngôn ngữ dùng trọng số và quy tắc locale.

| Mục tiêu | Lựa chọn thường xem xét |
| --- | --- |
| Khớp chính xác theo biểu diễn | Binary/deterministic comparison |
| Sắp xếp tên theo ngôn ngữ | Linguistic collation phù hợp locale |
| Không phân biệt hoa/thường | Case-insensitive collation hoặc phép biến đổi được định nghĩa |
| Không phân biệt dấu | Accent-insensitive collation hoặc search key riêng |
| Khóa kỹ thuật ASCII | Binary/deterministic comparison |
| Tìm kiếm thân thiện người dùng | Collation/search strategy theo yêu cầu sản phẩm |

Không có một collation tốt nhất cho mọi cột. Một cột email, một tên người, một mã sản phẩm và một khóa kỹ thuật có thể cần quy tắc khác nhau.

### 9.1. Equality và ORDER BY là hai hành vi cần test

Collation quyết định thứ tự sắp xếp và phép so sánh. Hai giá trị có thể có cùng trọng số ở mức so sánh nào đó nhưng thứ tự tie-break hoặc cách xử lý khác nhau theo DBMS.

Khi cần phân trang ổn định, thêm khóa duy nhất làm tie-break:

```sql
SELECT customer_id, full_name
FROM app.customers
ORDER BY full_name, customer_id;
```

Nếu chỉ ORDER BY full_name và nhiều tên được coi là bằng nhau theo collation, thứ tự giữa chúng có thể không ổn định.

## 10. Test fixture Unicode có chủ đích

Một bộ dữ liệu tốt phải chứa nhiều dạng khác nhau, không chỉ một vài tên có dấu.

```sql
CREATE TABLE unicode_people (
    person_id INTEGER PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    external_code VARCHAR(100)
);

INSERT INTO unicode_people(person_id, display_name, external_code)
VALUES
    (1, 'Nguyễn Ánh', 'A-01'),
    (2, 'NGUYỄN ÁNH', 'A-02'),
    (3, 'Nguyen Anh', 'A-03'),
    (4, 'Đặng Thị Mai', 'A-04'),
    (5, 'Dang Thi Mai', 'A-05'),
    (6, 'ắ', 'A-06'),
    (7, 'a' || CHR(774) || CHR(769), 'A-07'),
    (8, '😀', 'A-08');
```

Đoạn INSERT dùng CHR theo ví dụ PostgreSQL; cú pháp tạo chuỗi code point khác nhau ở DBMS khác. Trong test Java, có thể tạo dạng dựng sẵn/phân rã bằng Unicode escape và Normalizer để fixture nhất quán.

### 10.1. Những cặp cần thử

- Nguyễn Ánh và NGUYỄN ÁNH: case.
- Nguyễn Ánh và Nguyen Anh: dấu.
- Đặng và Dang: chữ đ và d.
- ắ và dạng phân rã: normalization.
- A và Ａ: ký tự ASCII/full-width.
- 😀 và các emoji kết hợp: supplementary code point/grapheme.

### 10.2. Dùng dữ liệu giả, không phụ thuộc một tên thật

Fixture nên nhỏ, có nhãn dễ đọc và tái tạo được. Không dùng thông tin cá nhân thật trong test Unicode nếu không cần thiết.

### 10.3. Ghi rõ kỳ vọng theo collation

Đừng chỉ lưu dữ liệu. Hãy ghi mỗi cặp cần:

- Bằng nhau hay khác nhau?
- Có được xem là duplicate không?
- Sort trước hay sau?
- LIKE có khớp không?
- Unique constraint có chấp nhận cả hai không?

## 11. Kiểm thử normalization bằng Java

Tạo hai dạng của cùng một chữ:

```java
String composed = "\u1EAF";       // ắ
String decomposed = "a\u0306\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(
    Normalizer.normalize(composed, Normalizer.Form.NFC)
        .equals(
            Normalizer.normalize(decomposed, Normalizer.Form.NFC)
        )
); // true
```

### 11.1. Test round-trip

```java
String input = "Nguyễn Ánh ắ 😀";

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO unicode_test(id, value) VALUES (?, ?)")) {
    ps.setInt(1, 1);
    ps.setString(2, input);
    ps.executeUpdate();
}

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT value FROM unicode_test WHERE id = ?")) {
    ps.setInt(1, 1);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String output = rs.getString(1);
            if (!input.equals(output)) {
                throw new AssertionError("Unicode round-trip mismatch");
            }
        }
    }
}
```

So sánh chuỗi chính xác giúp phát hiện biến đổi trong quá trình truyền/lưu. Nếu ứng dụng chủ động chuẩn hóa khi ghi, test phải so với dạng chuẩn đã quy định thay vì luôn so với input ban đầu.

### 11.2. Test byte representation khi cần

```java
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);

String decoded = new String(
    utf8,
    StandardCharsets.UTF_8
);
```

Không dùng charset mặc định cho dữ liệu cần tái tạo chính xác.

### 11.3. Test cả chiều đọc và chiều ghi

Một INSERT đúng chưa chứng minh SELECT đúng; một API response đúng chưa chứng minh dữ liệu lưu giữ nguyên normalization. Kiểm tra cả round-trip Java → JDBC → DB → JDBC → Java.

## 12. Chuẩn hóa ở tầng ứng dụng hay database?

Có ba chiến lược phổ biến:

### Chiến lược A — Giữ nguyên chuỗi gốc

Lưu chính xác nội dung người dùng gửi. Khi tìm kiếm, dùng collation hoặc search key phù hợp.

Phù hợp khi cần giữ nguyên nội dung, tên chính thức hoặc dữ liệu pháp lý.

### Chiến lược B — Chuẩn hóa khi ghi

Chuẩn hóa về NFC trước khi lưu để giảm khác biệt biểu diễn tương đương.

```java
String canonical = Normalizer.normalize(
    input,
    Normalizer.Form.NFC
);
```

Phù hợp khi ứng dụng kiểm soát toàn bộ đường ghi và có chính sách rõ. Cần xử lý dữ liệu cũ và mọi writer khác.

### Chiến lược C — Lưu nguyên bản và thêm search key

Ví dụ có hai cột:

- display_name: giá trị gốc để hiển thị.
- display_name_search: dạng chuẩn hóa/fold theo quy tắc tìm kiếm.

Điều này cho phép tìm kiếm linh hoạt mà không phá dữ liệu gốc. Search key cần được tạo thống nhất, có version và index phù hợp.

### 12.1. Không trộn chiến lược tùy tiện

Nếu một API chuẩn hóa NFC, một batch import giữ NFD, còn một service khác xóa dấu, cùng một cột có thể chứa nhiều chính sách không tương thích.

Hãy đặt quy tắc tại một lớp dùng chung và áp dụng cho mọi đường ghi.

## 13. Case folding và locale

Chuyển chữ hoa/thường không đơn giản là thay mọi chữ A-Z.

Ví dụ tiếng Thổ Nhĩ Kỳ có các chữ I, İ, ı, i với quy tắc hoa/thường khác tiếng Anh. Một số ngôn ngữ có phép chuyển case phụ thuộc ngữ cảnh.

Java:

```java
String technicalKey = input.toLowerCase(Locale.ROOT);
```

Locale.ROOT phù hợp cho một số khóa kỹ thuật cần phép chuyển chữ trung lập theo locale. Nó không thay thế collation ngôn ngữ cho tên người dùng.

### 13.1. Không dùng locale mặc định của máy

```java
input.toLowerCase()
```

dùng default locale của JVM. Kết quả có thể khác giữa môi trường máy developer và production.

Nếu thật sự cần chuyển case theo tiếng Việt hoặc locale cụ thể, chỉ định locale rõ và kiểm thử.

### 13.2. Lowercase không phải Unicode case folding hoàn chỉnh

Một số phép so sánh ngôn ngữ cần full case folding hoặc collation của ICU/DBMS. toLowerCase(Locale.ROOT) không đảm bảo mô phỏng chính xác mọi quy tắc database.

### 13.3. Không lưu lowercase thay cho tên hiển thị

Giữ giá trị gốc để hiển thị; nếu cần khóa tìm kiếm không phân biệt case, tạo cột/key riêng hoặc dùng collation phù hợp.

## 14. Accent-insensitive search và giới hạn của việc bỏ dấu

Một yêu cầu thường gặp: tìm Nguyen có thể trả Nguyễn.

Có thể thực hiện bằng collation accent-insensitive hoặc một search key do ứng dụng tạo. Tuy nhiên:

- a và á có thể được coi là tương đương trong phép tìm kiếm.
- đ không nhất thiết được chuyển thành d bởi việc bỏ combining marks.
- Nhiều ngôn ngữ có dấu/ký tự không thể xử lý bằng một quy tắc xóa dấu đơn giản.
- Collation khác nhau có thể cho kết quả khác.
- Unique index dùng AI có thể gây xung đột tên.

### 14.1. Tách tìm kiếm và tính duy nhất

Một hệ thống có thể cho phép tìm kiếm không dấu nhưng vẫn yêu cầu mã định danh chính xác.

Không dùng cùng một key AI để tạo unique constraint nếu nghiệp vụ không muốn hợp nhất các tên khác nhau.

### 14.2. Search key có thể cần thuật toán riêng

Nếu sản phẩm yêu cầu đ khớp d, hãy quy định rõ mapping đó. Test các cặp chữ, hoa/thường, dấu và normalization. Đừng cho rằng ICU hoặc một collation bất kỳ sẽ tự thực hiện đúng chính sách mong muốn.

## 15. Độ rộng ký tự, kana và các thuộc tính collation khác

Ngoài case và accent, một số collation hỗ trợ phân biệt:

- **Width sensitivity (WS):** phân biệt dạng full-width và half-width.
- **Kana sensitivity (KS):** phân biệt các dạng kana trong tiếng Nhật.
- **Variation selectors:** có thể ảnh hưởng cách so sánh một số ký tự/emoji.
- **Punctuation/space weighting:** cách xử lý dấu câu và khoảng trắng.

Các thuộc tính này thường xuất hiện trong collation của SQL Server/ICU hoặc quy tắc locale.

### 15.1. Không giả định mọi DBMS có cùng các suffix

Tên collation và suffix không portable. Ví dụ CI/AI là cách đặt tên quen thuộc trong SQL Server; MySQL dùng họ tên collation khác; PostgreSQL ICU dùng locale tag/strength.

### 15.2. Test đúng loại ký tự ứng dụng thực sự nhận

Nếu sản phẩm chỉ nhận tên tiếng Việt, tập test tập trung vào Unicode Latin mở rộng và dấu kết hợp. Nếu hỗ trợ tiếng Nhật, Hàn, Ả Rập hoặc emoji, cần thêm fixture tương ứng.

## 16. Unique constraint và collation

Giả sử cột username có unique constraint. Câu hỏi là hai giá trị nào được coi là trùng?

Nếu collation case-insensitive, Admin và admin có thể xung đột. Nếu accent-insensitive, Jose và José có thể xung đột tùy collation.

### 16.1. Test trước khi tạo unique index

Trước khi đổi collation, tìm nhóm có thể va chạm theo collation mới. Cú pháp kiểm tra phụ thuộc DBMS, nhưng ý tưởng là GROUP BY/partition theo biểu thức so sánh dự định.

Không tạo unique index trên dữ liệu production rồi mới phát hiện hàng loạt giá trị trùng theo collation mới.

### 16.2. Unique constraint không nhất thiết giống phép so sánh Java

Java String.equals so sánh chuỗi theo code unit; database unique index dùng quy tắc của DBMS/collation. Hai tầng có thể đưa ra kết luận khác nhau.

Không kiểm tra trùng ở Java bằng equals rồi tin rằng database chắc chắn chấp nhận INSERT.

### 16.3. NULL trong unique constraint

Cách xử lý nhiều NULL trong unique constraint cũng khác nhau giữa DBMS và có thể có lựa chọn đặc biệt theo phiên bản. Đây là một quy tắc khác với Unicode collation; kiểm thử riêng.

## 17. Index và collation

Index chuỗi thường được xây theo quy tắc so sánh/collation của cột hoặc biểu thức.

Nếu query áp dụng hàm hoặc COLLATE khác với index, optimizer có thể không dùng index hiện có theo cách mong muốn.

Ví dụ:

```sql
SELECT person_id
FROM people
WHERE LOWER(display_name) = LOWER(?);
```

Một B-tree index thông thường trên display_name không nhất thiết đáp ứng hiệu quả biểu thức LOWER(display_name).

### 17.1. Expression/function index

Một số DBMS hỗ trợ index trên biểu thức:

```sql
CREATE INDEX people_name_lower_idx
ON people (LOWER(display_name));
```

Cú pháp và khả năng dùng index phụ thuộc DBMS. PostgreSQL hỗ trợ expression index; các hệ khác có computed/persisted column hoặc function-based index.

### 17.2. Search key được index

Nếu ứng dụng có cột display_name_search, có thể tạo index riêng trên cột đó. Phải đảm bảo writer cập nhật đồng bộ cả giá trị gốc và search key.

### 17.3. Collation thay đổi có thể cần rebuild index

Nếu collation provider hoặc phiên bản ICU thay đổi quy tắc sắp xếp, index có thể không còn phản ánh thứ tự mới. PostgreSQL có cơ chế phát hiện collation version mismatch ở các trường hợp hỗ trợ; cần đánh giá và rebuild/reindex theo hướng dẫn version.

Không nâng cấp thư viện collation rồi giả định mọi index tự động được xây lại.

## 18. LIKE, prefix search và Unicode

LIKE không phải lúc nào cũng có cùng semantics với phép so sánh bằng của collation.

Ví dụ:

```sql
SELECT person_id, display_name
FROM people
WHERE display_name LIKE 'Nguyễn%';
```

Kết quả phụ thuộc collation, DBMS và hỗ trợ pattern matching. Một collation không phân biệt dấu trong equality chưa chắc làm LIKE hoạt động đúng như mong đợi ở mọi DBMS/version.

### 18.1. Test cả pattern và giá trị

Các test nên bao gồm:

- Prefix có dấu so với prefix không dấu.
- Chữ hoa/thường.
- Ký tự dựng sẵn và phân rã.
- % và _ là wildcard hay literal.
- Ký tự ngoài BMP.
- Kết quả trên đúng collation cột và expression.

### 18.2. Escape wildcard khi tìm literal

Bind parameter bảo vệ cấu trúc SQL, nhưng % và _ vẫn có ý nghĩa pattern. Nếu cần tìm literal, dùng ESCAPE và xử lý ký tự escape theo dialect.

### 18.3. PostgreSQL pattern operators

Một số kiểu collation, đặc biệt nondeterministic ICU collation, có giới hạn khác nhau đối với pattern matching theo phiên bản PostgreSQL. Kiểm tra đúng version và operator được dùng; có thể cần áp dụng collation deterministic cho biểu thức pattern hoặc dùng search strategy khác.

## 19. JOIN và GROUP BY dưới collation

Collation có thể ảnh hưởng việc ghép chuỗi, nhóm dữ liệu và loại trùng.

```sql
SELECT a.person_id, b.person_id
FROM source_people AS a
JOIN imported_people AS b
  ON a.display_name = b.display_name;
```

Nếu hai cột dùng collation khác nhau, DBMS có thể áp dụng quy tắc từ một phía, báo lỗi collation conflict, yêu cầu COLLATE tường minh hoặc dùng phép so sánh khác với mong đợi của ứng dụng.

### 19.1. COLLATE trong biểu thức

Một số DBMS cho phép:

```sql
SELECT *
FROM source_people AS a
JOIN imported_people AS b
  ON a.display_name COLLATE some_collation =
     b.display_name COLLATE some_collation;
```

Tên collation và cú pháp cần thay theo DBMS. Không thể bind tên collation bằng placeholder.

### 19.2. GROUP BY có thể gộp giá trị nhìn khác nhau

Nếu collation coi AN và An bằng nhau, GROUP BY có thể nhóm chúng cùng nhau. Nếu báo cáo cần phân biệt nguyên văn, dùng phép so sánh deterministic/binary hoặc một khóa biểu diễn phù hợp.

### 19.3. DISTINCT cũng theo quy tắc so sánh

SELECT DISTINCT display_name có thể trả số giá trị ít hơn số chuỗi byte khác nhau nếu collation xem một số dạng là tương đương.

## 20. PostgreSQL: encoding và collation

PostgreSQL có server encoding, client encoding và collation riêng.

### 20.1. Kiểm tra encoding

```sql
SHOW server_encoding;
SHOW client_encoding;

SELECT datname, pg_encoding_to_char(encoding)
FROM pg_database
WHERE datname = current_database();
```

Với ứng dụng tiếng Việt và dữ liệu đa ngôn ngữ, UTF8 thường là lựa chọn phù hợp. Không thể đổi server/database encoding tùy ý bằng một lệnh ALTER DATABASE đơn giản sau khi dữ liệu đã được lưu.

### 20.2. Kiểm tra collation

```sql
SELECT
    datname,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
```

Kiểm tra collation của cột qua catalog hoặc information_schema phù hợp.

### 20.3. ICU collation

Nếu PostgreSQL được build với ICU, có thể tạo collation dựa trên locale ICU. Ví dụ minh họa:

```sql
CREATE COLLATION vi_search_ci (
    provider = icu,
    locale = 'vi-u-ks-level1',
    deterministic = false
);
```

Đây là ví dụ cấu hình; locale tag, ICU availability và semantics cần được kiểm chứng trên đúng phiên bản. Strength cấp thấp có thể bỏ qua nhiều khác biệt, bao gồm case/accent theo quy tắc ICU.

### 20.4. Deterministic và nondeterministic

- Deterministic collation phân biệt các chuỗi khác byte ngay cả khi linguistic comparison có trọng số tương tự, bằng cách có tie-break xác định.
- Nondeterministic collation có thể coi các chuỗi khác biểu diễn là bằng nhau theo quy tắc locale.

Nondeterministic collation có thể ảnh hưởng unique index, equality, index support và pattern operators. Đọc tài liệu PostgreSQL version đang chạy trước khi dùng làm collation cho khóa duy nhất.

### 20.5. Collation C

COLLATE "C" cung cấp so sánh/sắp xếp theo quy tắc C đơn giản, thường hữu ích cho khóa kỹ thuật và so sánh xác định. Nó không phải thứ tự từ điển tiếng Việt.

## 21. MySQL: charset và collation ở nhiều cấp

MySQL cho phép cấu hình character set/collation ở server, database, table, column và expression.

### 21.1. Kiểm tra cấu hình

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SHOW CREATE TABLE unicode_people;
```

Đừng chỉ kiểm tra database default; cột cũ có thể đang dùng charset/collation khác.

### 21.2. utf8mb4

Với dữ liệu Unicode rộng, utf8mb4 thường là lựa chọn phù hợp trong MySQL. utf8 từng là alias cho utf8mb3 trong nhiều phiên bản, không biểu diễn được toàn bộ Unicode như utf8mb4.

Ví dụ:

```sql
CREATE TABLE unicode_people (
    person_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
);
```

Collation utf8mb4_0900_ai_ci thuộc họ MySQL 8.0; không giả định nó có trên MySQL cũ hoặc MariaDB.

### 21.3. Suffix collation

Các tên MySQL có thể chứa thuộc tính như:

- _ai: accent-insensitive.
- _as: accent-sensitive.
- _ci: case-insensitive.
- _cs: case-sensitive.
- _bin: binary-style comparison.

Tên và thuộc tính cụ thể tùy version/family. Kiểm tra SHOW COLLATION.

### 21.4. PAD SPACE và NO PAD

Collation có thể có quy tắc xử lý khoảng trắng cuối chuỗi khác nhau. Một số collation cũ có PAD SPACE; nhiều collation Unicode 9.0 mới có NO PAD. Điều này ảnh hưởng equality/unique và cần test với chuỗi có trailing spaces.

### 21.5. Chọn collation theo mục tiêu

Một cột tên hiển thị có thể cần collation ngôn ngữ; cột token/mã kỹ thuật có thể cần binary hoặc collation xác định. Không áp dụng AI/CI cho toàn database mà không xem tác động unique và join.

## 22. SQL Server: Unicode types và collations

SQL Server có kiểu nchar/nvarchar lưu Unicode theo UTF-16. char/varchar phụ thuộc code page/collation, nhưng từ SQL Server 2019 có hỗ trợ UTF-8 collations cho varchar.

### 22.1. NVARCHAR và literal N

```sql
CREATE TABLE dbo.UnicodePeople (
    PersonId INT PRIMARY KEY,
    DisplayName NVARCHAR(200) NOT NULL
);

INSERT INTO dbo.UnicodePeople(PersonId, DisplayName)
VALUES (1, N'Nguyễn Ánh');
```

Tiền tố N trên literal T-SQL chỉ ra Unicode string literal theo quy tắc SQL Server.

JDBC driver có mapping riêng cho NVARCHAR; dùng setNString khi phù hợp với kiểu national character, hoặc mapping String theo driver/schema đã kiểm thử.

### 22.2. UTF-8 VARCHAR

SQL Server 2019+ có các collation hỗ trợ UTF-8 cho varchar. Khả năng phụ thuộc collation được chọn; không có nghĩa mọi cột varchar tự động thành UTF-8.

### 22.3. Collation suffix

SQL Server có các thuộc tính thường thấy:

- _CI / _CS: case-insensitive / case-sensitive.
- _AI / _AS: accent-insensitive / accent-sensitive.
- _KS: kana sensitivity.
- _WS: width sensitivity.
- _SC: supplementary character support trong các collation hỗ trợ.
- _BIN2: binary code point comparison theo semantics SQL Server.

Tra cứu tên collation sẵn có:

```sql
SELECT name, description
FROM sys.fn_helpcollations()
WHERE name LIKE '%Vietnamese%';
```

### 22.4. Collation cấp database, column và expression

Có thể cấu hình ở nhiều cấp. Hai cột khác collation khi JOIN hoặc so sánh có thể gây collation conflict; dùng COLLATE tường minh nếu cần và có chính sách rõ.

### 22.5. Identifier và tempdb

Collation của database ảnh hưởng nhiều quy tắc tên đối tượng. Temporary table được tạo trong tempdb; khác biệt collation giữa database người dùng và tempdb có thể gây xung đột khi dùng cột chuỗi trong temp table nếu không xử lý collation phù hợp, chẳng hạn COLLATE DATABASE_DEFAULT trong những trường hợp thích hợp.

## 23. Oracle: character set, NLS và collation

Oracle phân biệt database character set và national character set.

### 23.1. AL32UTF8

AL32UTF8 là character set Unicode UTF-8 chuẩn của Oracle và thường là lựa chọn phù hợp cho database mới cần dữ liệu đa ngôn ngữ.

UTF8 trong Oracle là tên character set legacy với semantics khác AL32UTF8; không nên chọn nó chỉ vì tên giống UTF-8.

### 23.2. NCHAR/NVARCHAR2

Oracle có kiểu national character như NCHAR/NVARCHAR2 dùng national character set. Với nhiều hệ thống AL32UTF8, VARCHAR2 đã có thể lưu Unicode; chọn kiểu dựa trên schema và yêu cầu tương thích.

### 23.3. Kiểm tra NLS

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
);
```

Session có thể có NLS settings riêng:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter LIKE 'NLS_%';
```

### 23.4. NLS_SORT và NLS_COMP

Oracle có các tham số ảnh hưởng so sánh/sắp xếp ngôn ngữ, ví dụ NLS_SORT và NLS_COMP. Chúng có thể được đặt ở session hoặc dùng biểu thức/collation phù hợp.

Một số phiên bản Oracle hỗ trợ data-bound collation và cú pháp COLLATE; khả năng cụ thể phụ thuộc version/compatibility.

### 23.5. Function-based linguistic index

Nếu query dùng NLSSORT hoặc phép biến đổi linguistic, có thể cần function-based index tương ứng. Đừng đổi NLS_SORT rồi giả định index binary hiện có vẫn tối ưu.

### 23.6. Chuỗi rỗng

Oracle SQL truyền thống xử lý chuỗi ký tự độ dài 0 như NULL. Đây là khác biệt quan trọng với PostgreSQL/SQL Server và cần có test riêng trong repository/API.

## 24. SQLite: BINARY, NOCASE và ICU

SQLite có hệ thống collation tích hợp đơn giản hơn các server RDBMS.

Các collation phổ biến:

- BINARY: so sánh theo byte.
- NOCASE: không phân biệt hoa/thường theo phạm vi ASCII được hỗ trợ.
- RTRIM: bỏ qua khoảng trắng cuối trong so sánh theo quy tắc của nó.

### 24.1. NOCASE không phải Unicode case folding toàn diện

```sql
CREATE TABLE people (
    name TEXT COLLATE NOCASE
);
```

NOCASE tích hợp của SQLite không phải một collation ngôn ngữ Unicode đầy đủ. Các chữ ngoài ASCII như tiếng Việt có thể không được xử lý case-insensitive như mong đợi.

### 24.2. LIKE cũng có giới hạn Unicode

LIKE mặc định của SQLite thường không phân biệt ASCII case theo cách tích hợp, nhưng không tự cung cấp full Unicode case folding. Extension ICU có thể bổ sung hành vi Unicode phù hợp hơn.

### 24.3. Custom collation

Ứng dụng có thể đăng ký custom collation qua API SQLite. Cần bảo đảm mọi connection sử dụng database đều đăng ký cùng implementation trước khi query/index liên quan.

Nếu collation custom thay đổi semantics, index xây theo comparator cũ có thể cần rebuild.

### 24.4. Encoding database

SQLite hỗ trợ UTF-8 và UTF-16 database encoding. Kiểm tra:

```sql
PRAGMA encoding;
```

PRAGMA encoding không phải công cụ chuyển đổi tùy tiện một database đã có dữ liệu sang encoding khác.

## 25. Identifier có dấu là gì?

Identifier là tên đối tượng SQL:

- Database/catalog.
- Schema.
- Table.
- Column.
- Index.
- Constraint.
- Function/procedure.
- Alias.

Ví dụ:

```sql
CREATE TABLE khách_hàng (
    mã_khách_hàng BIGINT,
    họ_tên VARCHAR(200)
);
```

Một số DBMS có thể chấp nhận Unicode trong identifier, đặc biệt khi được quote. Nhưng điều đó không bảo đảm cùng tên chạy được trên mọi DBMS, migration tool, ORM, BI tool, shell script và hệ điều hành.

### 25.1. Identifier khác string literal

- Identifier: tên bảng/cột, được parser nhận diện theo quy tắc định danh.
- String literal: giá trị dữ liệu trong dấu nháy.
- Parameter: giá trị được bind qua JDBC.

Dấu quote identifier không phải cách quote giá trị dữ liệu; PreparedStatement không thay thế quy tắc quote tên cột.

### 25.2. Khuyến nghị cho schema dùng lâu dài

Ưu tiên identifier ASCII ổn định, ví dụ:

- customer_id
- display_name
- created_at
- invoice_line

Tên hiển thị cho người dùng có thể có dấu đầy đủ trong dữ liệu. Giữ tên schema ổn định giúp migration, driver, ORM và tích hợp đa hệ thống dễ tương thích.

### 25.3. Nếu bắt buộc có identifier Unicode

Dùng quy tắc quote chính xác của DBMS, kiểm thử DDL/DML, metadata, migration, backup/restore, ORM mapping và mọi công cụ truy cập. Không ghép tên do người dùng nhập trực tiếp vào SQL.

## 26. Quy tắc identifier giữa các DBMS

| DBMS | Quote identifier phổ biến | Quy tắc tên đáng chú ý |
| --- | --- | --- |
| PostgreSQL | Dấu nháy kép | Identifier không quote được fold về chữ thường; identifier quote giữ case |
| MySQL | Backtick | Độ nhạy hoa/thường của database/table name có thể phụ thuộc OS và lower_case_table_names; column name có quy tắc riêng |
| SQL Server | Ngoặc vuông hoặc dấu nháy kép khi QUOTED_IDENTIFIER phù hợp | Case sensitivity của identifier chịu ảnh hưởng collation và loại đối tượng |
| Oracle | Dấu nháy kép | Identifier không quote thường được fold về chữ hoa; quoted identifier giữ case |
| SQLite | Dấu nháy kép là cách quote chuẩn; còn hỗ trợ một số dạng khác | Identifier không phân biệt ASCII case trong parser; không nên dựa vào khác biệt Unicode hiếm |

### 26.1. PostgreSQL

```sql
CREATE TABLE Customer (
    Id BIGINT
);

CREATE TABLE "Customer" (
    "Id" BIGINT
);
```

Tên không quote được fold thành lowercase customer; tên quote giữ case Customer. Hai cách có thể tạo ra tên khác nhau.

### 26.2. Oracle

```sql
CREATE TABLE Customer (
    Id NUMBER
);
```

Tên không quote thường được lưu dưới dạng uppercase CUSTOMER, ID. Quoted identifier giữ đúng case và phải được quote đúng cách khi tham chiếu.

### 26.3. MySQL

```sql
CREATE TABLE \`order details\` (
    \`customer name\` VARCHAR(100)
);
```

Backtick cho phép tên có khoảng trắng hoặc từ khóa, nhưng dùng tên như vậy làm SQL khó portable và khó đọc.

### 26.4. SQL Server

```sql
CREATE TABLE [Order Details] (
    [Customer Name] NVARCHAR(100)
);
```

Dùng dấu ngoặc vuông để quote identifier; double quote cũng có thể dùng khi session/database bật QUOTED_IDENTIFIER theo quy tắc SQL Server.

### 26.5. SQLite

```sql
CREATE TABLE "customer details" (
    "display name" TEXT
);
```

Dù parser cho phép, identifier có dấu cách làm tăng nhu cầu quote trong mọi query. Tên ASCII snake_case thường dễ bảo trì hơn.

## 27. Collation dữ liệu không phải quy tắc case của identifier

Một database có collation CI có thể không phân biệt hoa/thường trong phép so sánh chuỗi dữ liệu. Tuy nhiên không suy ra tất cả DBMS sẽ áp dụng cùng quy tắc cho tên bảng/cột.

Identifier có thể chịu ảnh hưởng của:

- Database/instance collation.
- Parser folding.
- Quy tắc quote.
- Filesystem trên một số hệ thống.
- Metadata catalog.
- Quy tắc riêng của temporary database/schema.

**Test tên đối tượng riêng với test dữ liệu chuỗi.** Một phép SELECT trên cột tên có dấu chạy đúng không chứng minh identifier có dấu sẽ portable.

## 28. Từ khóa, dấu câu và identifier động

Tên bảng có khoảng trắng, dấu gạch ngang, chữ có dấu hoặc trùng từ khóa thường cần quote.

Ví dụ:

```sql
SELECT "tên khách hàng"
FROM "khách hàng";
```

Nhưng khi viết ứng dụng, không nên nhận identifier từ request rồi nối vào SQL:

```java
String sql = "SELECT * FROM " + requestTable;
```

PreparedStatement không bind được identifier. Nếu cần chọn bảng/cột động, dùng enum hoặc whitelist ánh xạ tới tên cố định do code quản lý.

### 28.1. Quote không tự chống mọi injection

Quote identifier đúng cách giúp parser xử lý tên, nhưng nếu tự xây tên từ input mà không whitelist, có thể vẫn tạo query sai hoặc nguy hiểm.

### 28.2. Metadata và ORM

Một số ORM chuyển identifier theo naming strategy, quote tự động hoặc fold case. Khi dùng Unicode identifier, kiểm tra DDL generated, metadata lookup và schema validation của ORM.

## 29. JDBC và Unicode string binding

JDBC String là Unicode text ở tầng Java. Driver chuyển đổi theo database protocol và kiểu cột.

### 29.1. setString

```java
ps.setString(1, "Nguyễn Ánh");
```

Thường dùng cho VARCHAR/TEXT và các kiểu chuỗi tương ứng theo mapping driver.

### 29.2. setNString

```java
ps.setNString(1, "Nguyễn Ánh");
```

Dùng cho kiểu national character data khi driver/DBMS hỗ trợ và schema cần, chẳng hạn NCHAR/NVARCHAR2 hoặc NVARCHAR trong một số hệ.

Không cần gọi setNString cho mọi cột chỉ vì dữ liệu có dấu; chọn theo kiểu cột và mapping JDBC của driver.

### 29.3. getString và getNString

Tương tự khi đọc:

```java
String value = rs.getString("display_name");
```

hoặc getNString cho kiểu national character khi phù hợp.

### 29.4. Không tự encode String thành byte[] để bind VARCHAR

Không nên:

```java
ps.setBytes(1, name.getBytes(StandardCharsets.UTF_8));
```

cho một cột VARCHAR chỉ vì muốn giữ Unicode. Nó có thể bind binary value hoặc gây chuyển đổi sai. Dùng setter chuỗi đúng kiểu; chỉ dùng byte[] khi cột thực sự là binary.

## 30. Kiểm tra encoding và collation khi gỡ lỗi

Khi dữ liệu hiển thị sai, ghi nhận thông tin ở cả client và database.

### 30.1. Java/JVM

```java
System.out.println(
    StandardCharsets.UTF_8.name()
);

System.out.println(
    Charset.defaultCharset()
);
```

Charset.defaultCharset() chỉ là thông tin môi trường, không nên làm charset mặc định cho file/network cần hợp đồng UTF-8.

### 30.2. PostgreSQL

```sql
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;
```

Với database/cột, kiểm tra catalog và collation được gán cụ thể.

### 30.3. MySQL

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
SHOW CREATE TABLE unicode_people;
SHOW COLLATION;
```

Kiểm tra server/database/table/column, không chỉ connection charset.

### 30.4. SQL Server

```sql
SELECT
    DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS database_collation;

SELECT
    c.name,
    c.collation_name
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID('dbo.UnicodePeople');
```

Kiểm tra kiểu cột nvarchar/varchar và collation thực tế.

### 30.5. Oracle

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET');

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter LIKE 'NLS_%';
```

Xác nhận cả database character set lẫn session linguistic settings.

### 30.6. SQLite

```sql
PRAGMA encoding;
```

Nếu dùng custom collation hoặc ICU extension, xác nhận extension/callback đã được đăng ký trên connection đang chạy.

## 31. Phân biệt mojibake, normalization và collation bug

Ba nhóm lỗi nhìn bề ngoài có thể giống nhau nhưng cách sửa khác nhau.

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Ký tự rác như Nguyá»... | Byte giải mã sai charset | Kiểm tra byte/charset ở từng chặng |
| Hai chuỗi nhìn giống nhưng = false | NFC/NFD hoặc binary comparison | In code point, normalize và so sánh |
| a và á không match như mong đợi | Collation accent-sensitive | Kiểm tra collation và query expression |
| AN và An không match | Case-sensitive collation | Kiểm tra case sensitivity |
| Unique insert từ chối tên khác byte | Collation coi hai giá trị bằng nhau | Kiểm tra collation/index |
| Dữ liệu đúng nhưng sort lạ | Locale/collation không phù hợp | ORDER BY với collation dự định |
| Emoji bị mất | Charset/driver/column không hỗ trợ | Round-trip supplementary code point |
| Identifier không tìm thấy | Folding/quoting/case rules | Xem metadata và SQL identifier thực tế |

### 31.1. Không sửa dữ liệu trước khi biết nguyên nhân

Nếu mojibake đã lưu trong database, chạy NFC hoặc đổi collation có thể chỉ chuẩn hóa chuỗi sai. Trước khi update hàng loạt, tìm nguồn gốc byte và backup dữ liệu.

### 31.2. Tạo một reproduction nhỏ

Một bảng test với vài chuỗi đại diện và một query tối thiểu thường giúp cô lập vấn đề nhanh hơn thay đổi cấu hình toàn database.

## 32. Sắp xếp tiếng Việt và phân trang ổn định

Sắp xếp theo ngôn ngữ cần collation phù hợp. ORDER BY display_name dùng collation của cột/biểu thức, nhưng thứ tự cụ thể phụ thuộc DBMS và locale.

### 32.1. Thêm khóa tie-break

```sql
SELECT person_id, display_name
FROM unicode_people
ORDER BY display_name, person_id;
```

Nếu nhiều tên được coi là tương đương theo collation, person_id giúp thứ tự ổn định hơn.

### 32.2. OFFSET pagination

```sql
SELECT person_id, display_name
FROM unicode_people
ORDER BY display_name, person_id
OFFSET 20 ROWS
FETCH NEXT 20 ROWS ONLY;
```

Cú pháp pagination khác nhau giữa DBMS. Khi collation thay đổi, vị trí các hàng có thể thay đổi và page boundary có thể dịch chuyển.

### 32.3. Keyset pagination

Với collation và tie-break ổn định, keyset pagination có thể dùng giá trị cuối trang và khóa phụ. Predicate so sánh phải dùng cùng semantics với ORDER BY; không tự dùng Java String.compareTo để tạo cursor cho database linguistic sort.

### 32.4. Nâng cấp ICU/OS có thể đổi sort order

Nếu collation dựa trên thư viện locale, phiên bản thư viện có thể thay đổi thứ tự. Với index và cursor lưu lâu, cần kiểm tra tác động khi nâng cấp môi trường.

## 33. Unicode và unique key cho email, username, mã sản phẩm

Không áp dụng cùng chính sách cho mọi loại chuỗi.

### 33.1. Email

Email có quy tắc chuẩn riêng; phần domain và local part có những đặc điểm khác nhau. Không mặc định mọi email đều nên được lowercase toàn bộ hoặc bỏ dấu.

Nếu sản phẩm chọn không phân biệt case khi đăng nhập, phải định nghĩa chính sách ở application/database và bảo đảm unique index dùng cùng chính sách.

### 33.2. Username

Có thể cần case-insensitive uniqueness, nhưng có thể giữ cách viết gốc để hiển thị. Dùng normalized key riêng hoặc collation phù hợp và kiểm tra collision trước migration.

### 33.3. Mã sản phẩm

Mã thường là identifier kỹ thuật. Có thể dùng binary/deterministic comparison và quy tắc uppercase ASCII nếu nghiệp vụ yêu cầu. Không dùng accent-insensitive collation chỉ vì tên sản phẩm có dấu.

### 33.4. Tên người

Tên người cần giữ nguyên dấu, khoảng trắng và Unicode. Search không dấu có thể là chức năng hỗ trợ; không biến search key thành định danh pháp lý.

## 34. Di chuyển collation hoặc charset

Thay charset/collation trên hệ thống đang chạy là thay đổi dữ liệu và index, không chỉ đổi một setting.

### 34.1. Trước khi thay đổi

- Kiểm kê charset/collation ở database/table/column.
- Xác định dữ liệu hiện tại có mojibake không.
- Tìm duplicate theo collation đích.
- Kiểm tra index, unique constraint, foreign key và view phụ thuộc.
- Kiểm tra driver/ORM và ứng dụng.
- Đo dung lượng, lock và thời gian migration.
- Backup và thử restore.

### 34.2. Thử trên bản sao

Tạo bản sao dữ liệu đại diện, đổi collation/charset, rebuild index và chạy test equality/order/unique. Đừng thử lần đầu trên production.

### 34.3. Rebuild index

Một số DBMS cần rebuild index sau thay đổi collation hoặc provider version. Dùng lệnh đúng DBMS và kiểm tra index validity sau thao tác.

### 34.4. Đổi encoding có thể không đơn giản

Database encoding có thể được cố định khi tạo database. Việc chuyển đổi có thể cần dump/restore hoặc quy trình chuyển đổi riêng; không chạy UPDATE chuyển byte tùy tiện.

### 34.5. Rollback plan

Nếu unique collision hoặc sort order thay đổi ngoài dự kiến, cần khả năng quay về collation/index/schema cũ hoặc phục hồi từ backup. Đổi collation có thể làm thay đổi logic đăng nhập và khóa duy nhất, nên phải có kế hoạch nghiệp vụ.

## 35. Kiểm thử end-to-end từ API đến database

Một test Unicode hoàn chỉnh đi qua các lớp:

```text
JSON request
    -> HTTP decoding
    -> Java String
    -> validation/normalization
    -> JDBC binding
    -> database charset/collation
    -> stored value
    -> ResultSet mapping
    -> JSON response
```

### 35.1. Kiểm tra HTTP

Đảm bảo request body được decode đúng UTF-8. Test cả JSON escape như \u1EAF và ký tự Unicode literal nếu client hỗ trợ.

### 35.2. Kiểm tra validation

Không dùng regex ASCII-only như [A-Za-z ]+ nếu sản phẩm cần chấp nhận tên tiếng Việt. Định nghĩa rõ loại ký tự, khoảng trắng, dấu nối và ký tự hợp lệ.

### 35.3. Kiểm tra JDBC

Dùng setString/setNString phù hợp schema. Không tự chuyển thành bytes cho cột text.

### 35.4. Kiểm tra database

Xác nhận charset/collation cột, lưu và đọc lại. Kiểm tra uniqueness và query behavior.

### 35.5. Kiểm tra response

Đảm bảo serializer/HTTP response giữ Unicode, không biến ký tự thành ? hoặc mojibake.

## 36. Tạo bộ test Unicode có thể tái lập

Nên đặt fixture thành một tập nhỏ có nhãn:

| ID | Giá trị | Mục tiêu |
| ---: | --- | --- |
| 1 | Nguyễn Ánh | Tiếng Việt dựng sẵn |
| 2 | NGUYỄN ÁNH | Khác hoa/thường |
| 3 | Nguyen Anh | Không dấu |
| 4 | Đặng Thị Mai | Chữ đ và dấu |
| 5 | Dang Thi Mai | d thường thay cho đ |
| 6 | ắ | Dạng dựng sẵn |
| 7 | a + combining breve + acute | Dạng phân rã |
| 8 | A và Ａ | ASCII/full-width |
| 9 | 😀 | Supplementary code point |
| 10 | 👩‍💻 | Grapheme cluster có ZWJ |
| 11 | O'Connor | Dấu nháy trong dữ liệu |
| 12 | A + khoảng trắng cuối | Trailing space |

### 36.1. Không chỉ assert hiển thị

Mỗi fixture nên có test round-trip byte/chuỗi, equality, sort position, LIKE/prefix, DISTINCT/GROUP BY, unique insert, JOIN, API JSON và index/plan nếu quan trọng.

### 36.2. Test theo từng collation

Một test cần ghi rõ DBMS/version, charset, collation và driver version. Kết quả collation ở môi trường A không tự áp dụng cho môi trường B.

## 37. Gợi ý test SQL cho từng loại hành vi

### 37.1. Round-trip

```sql
INSERT INTO unicode_people(person_id, display_name)
VALUES (100, 'Nguyễn Ánh');

SELECT person_id, display_name
FROM unicode_people
WHERE person_id = 100;
```

So sánh chuỗi trả về với input đã chuẩn hóa theo chính sách ứng dụng.

### 37.2. Equality

```sql
SELECT person_id
FROM unicode_people
WHERE display_name = 'Nguyen Anh';
```

Kết quả phụ thuộc collation. Test riêng case/accent/normalization.

### 37.3. ORDER BY

```sql
SELECT person_id, display_name
FROM unicode_people
ORDER BY display_name, person_id;
```

Ghi lại thứ tự mong muốn theo locale sản phẩm.

### 37.4. LIKE

```sql
SELECT person_id
FROM unicode_people
WHERE display_name LIKE 'Nguy%';
```

Test prefix có dấu/không dấu và wildcard literal.

### 37.5. DISTINCT và GROUP BY

```sql
SELECT display_name, COUNT(*)
FROM unicode_people
GROUP BY display_name
ORDER BY display_name;
```

Kiểm tra những giá trị collation coi là bằng nhau có được gộp đúng yêu cầu không.

### 37.6. Unique constraint

Tạo bảng test riêng với collation dự định, insert các cặp case/accent/NFC-NFD và ghi nhận cặp nào xung đột. Không test collision bằng cách thay đổi unique index production.

## 38. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Dấu tiếng Việt thành ? | Charset/cột/driver không hỗ trợ | Kiểm tra encoding từng lớp, schema và driver |
| Chuỗi thành mojibake | Decode sai charset | Truy lại byte và encoding nguồn |
| Chuỗi nhìn giống nhưng không bằng | NFC/NFD | In code point, chuẩn hóa theo policy |
| Tìm kiếm không dấu không hoạt động | Collation accent-sensitive | Chọn collation/search key phù hợp |
| đ không khớp d | Xóa combining mark không xử lý chữ đ | Định nghĩa mapping nghiệp vụ riêng |
| Unique insert bị từ chối | Collation coi hai giá trị bằng nhau | Kiểm tra unique index/collation và duplicate |
| ORDER BY tiếng Việt lạ | Locale/collation không phù hợp | Dùng collation locale đã kiểm thử |
| LIKE khác equality | Pattern operator có semantics riêng | Test đúng DBMS/version/operator |
| SQL Server collation conflict | Hai expression/cột khác collation | COLLATE tường minh hoặc thống nhất schema |
| SQLite NOCASE không nhận tiếng Việt | NOCASE tích hợp giới hạn ASCII | ICU/custom collation hoặc search key |
| Identifier không tìm thấy | Folding/quote/case mismatch | Kiểm tra catalog và quote đúng |
| Temp table lỗi collation | tempdb khác database collation | Chỉ định COLLATE DATABASE_DEFAULT khi phù hợp |
| Emoji bị cắt | Charset hoặc cắt chuỗi theo UTF-16 char | Kiểm tra supplementary support và grapheme |
| Query mất index | LOWER/COLLATE expression khác index | Expression/function index hoặc search column |
| Sau upgrade sort thay đổi | ICU/OS collation version thay đổi | Kiểm tra collation version và rebuild index |

## 39. Nguyên tắc thiết kế cho ứng dụng đa hệ quản trị

Một ứng dụng hỗ trợ nhiều DBMS nên định nghĩa chính sách Unicode ở mức domain, rồi ánh xạ sang từng dialect.

### 39.1. Tách giá trị gốc và khóa tìm kiếm

Giữ tên gốc để hiển thị. Nếu cần tìm không dấu/case-insensitive, tạo search key riêng theo thuật toán có version.

### 39.2. Định nghĩa collation cho từng trường

Không chọn một collation duy nhất cho toàn hệ thống. Email, username, tên người, mã kỹ thuật và mô tả có thể cần semantics khác nhau.

### 39.3. Identifier ASCII ổn định

Dùng tên bảng/cột ASCII snake_case để tăng khả năng tương thích. Tên hiển thị đa ngôn ngữ nên nằm trong dữ liệu hoặc metadata.

### 39.4. Parameterize mọi giá trị

Unicode input không làm thay đổi nguyên tắc SQL injection. Dùng PreparedStatement và setter phù hợp.

### 39.5. Không giả định kết quả giống nhau giữa DBMS

Viết integration test theo matrix DBMS/version/collation. Nếu cần semantics giống nhau tuyệt đối, cân nhắc chuẩn hóa/search key ở application layer và dùng phép so sánh deterministic cho key đó.

### 39.6. Ghi version của thuật toán search key

Nếu thuật toán bỏ dấu/case folding thay đổi, có thể cần backfill search key và rebuild index. Lưu version giúp migration có kiểm soát.

## 40. Bài tập thực hành có lời giải

Các bài tập dưới đây dùng Java và SQL. Khi chạy, ghi rõ DBMS, version, charset và collation; không mặc định kết quả so sánh giống nhau trên mọi hệ quản trị.

### Bài 1. String.length() của A😀 là bao nhiêu?

```java
String value = "A😀";
System.out.println(value.length());
```

**Đáp án:** 3 UTF-16 code units; codePointCount trả 2 code points.

### Bài 2. Hai dạng của ắ có equals không?

```java
String a = "\u1EAF";
String b = "a\u0306\u0301";
System.out.println(a.equals(b));
```

**Đáp án:** false vì chuỗi có biểu diễn code unit khác nhau.

### Bài 3. Chuẩn hóa NFC

```java
String normalized = Normalizer.normalize(
    b, Normalizer.Form.NFC
);
```

**Đáp án:** Chuỗi được chuẩn hóa về NFC; với ví dụ này có thể so sánh bằng với dạng dựng sẵn.

### Bài 4. NFC có xóa dấu không?

**Đáp án:** Không. NFC chuẩn hóa cách biểu diễn, không chuyển ắ thành a.

### Bài 5. NFD có tự chuyển đ thành d không?

**Đáp án:** Không theo quy tắc bỏ combining marks thông thường. đ là code point riêng; nếu muốn khớp d, phải định nghĩa mapping riêng.

### Bài 6. UTF-8 có thể lưu emoji không?

**Đáp án:** Có, UTF-8 mã hóa code point Unicode ngoài BMP bằng tối đa 4 byte. Cột/driver/database vẫn phải hỗ trợ đầy đủ.

### Bài 7. Vì sao không nên dùng String.length để giới hạn số ký tự người dùng?

**Đáp án:** Nó đếm UTF-16 code unit, không đếm grapheme cluster; emoji và chữ có dấu kết hợp có thể gồm nhiều code unit/code point.

### Bài 8. Collation CI nghĩa là gì?

**Đáp án:** Case-insensitive: phép so sánh theo collation không phân biệt một số khác biệt hoa/thường theo quy tắc của DBMS.

### Bài 9. Collation AI nghĩa là gì?

**Đáp án:** Accent-insensitive: phép so sánh có thể bỏ qua khác biệt dấu theo quy tắc locale/collation. Không có nghĩa dữ liệu lưu bị xóa dấu.

### Bài 10. Hai chuỗi khác byte có thể xung đột unique không?

**Đáp án:** Có. Nếu collation/index coi chúng bằng nhau, unique constraint có thể từ chối giá trị thứ hai.

### Bài 11. Java equals có giống database equality không?

**Đáp án:** Không nhất thiết. Java String.equals so sánh chuỗi theo biểu diễn UTF-16; database dùng collation và semantics của DBMS.

### Bài 12. Tại sao cần test NFC và NFD?

**Đáp án:** Người dùng/nguồn import có thể gửi hai biểu diễn Unicode tương đương; binary comparison có thể coi chúng khác nhau nếu không chuẩn hóa hoặc dùng collation phù hợp.

### Bài 13. MySQL utf8mb4 khác utf8mb3 thế nào?

**Đáp án:** utf8mb4 hỗ trợ toàn bộ Unicode code point qua tối đa 4 byte; utf8mb3 chỉ hỗ trợ BMP. Alias utf8 có lịch sử phụ thuộc version và không nên giả định là utf8mb4.

### Bài 14. SQL Server NVARCHAR dùng gì?

**Đáp án:** Lưu Unicode theo UTF-16. Các kiểu varchar UTF-8 cần collation UTF-8 hỗ trợ, từ SQL Server 2019 trở lên.

### Bài 15. Oracle AL32UTF8 khác UTF8 legacy thế nào?

**Đáp án:** AL32UTF8 là UTF-8 chuẩn của Oracle. UTF8 legacy có semantics khác; chọn AL32UTF8 cho database Unicode mới theo khuyến nghị phù hợp.

### Bài 16. SQLite NOCASE có full Unicode case folding không?

**Đáp án:** Không. NOCASE tích hợp chủ yếu xử lý ASCII; cần ICU/custom collation nếu cần Unicode case-insensitive đầy đủ.

### Bài 17. PostgreSQL identifier không quote được fold thế nào?

**Đáp án:** Fold thành chữ thường. Identifier quote bằng dấu nháy kép giữ case đã viết.

### Bài 18. Oracle identifier không quote được fold thế nào?

**Đáp án:** Thường fold thành chữ hoa; quoted identifier giữ case.

### Bài 19. PreparedStatement có bind tên cột không?

**Đáp án:** Không. Placeholder bind giá trị; identifier động cần whitelist và quoting theo DBMS.

### Bài 20. Dữ liệu hiển thị mojibake có sửa bằng đổi collation không?

**Đáp án:** Không. Cần xác định byte/encoding đã bị giải mã sai ở đâu và phục hồi nội dung trước; collation chỉ quy định so sánh/sắp xếp.

### Bài 21. setString có đủ cho mọi cột Unicode không?

**Đáp án:** Không nhất thiết. Chọn setString/setNString theo kiểu cột và mapping driver; kiểm thử round-trip.

### Bài 22. Vì sao setBytes(name.getBytes(UTF_8)) không phải cách bind VARCHAR?

**Đáp án:** Nó bind binary parameter, không phải string parameter. Dùng setString cho cột text; dùng setBytes cho cột binary.

### Bài 23. Vì sao ORDER BY cần khóa tie-break?

**Đáp án:** Nhiều chuỗi có thể bằng nhau theo collation; thêm khóa duy nhất giúp thứ tự phân trang ổn định hơn.

### Bài 24. LOWER(column) có thể ảnh hưởng index không?

**Đáp án:** Có thể. Index thông thường trên column không nhất thiết phục vụ biểu thức LOWER; cân nhắc expression/function index hoặc search key.

### Bài 25. Collation thay đổi có thể cần rebuild index không?

**Đáp án:** Có. Nếu quy tắc sort/equality thay đổi theo collation/provider version, index cũ có thể không phản ánh thứ tự mới.

### Bài 26. SQL Server temp table bị collation conflict vì sao?

**Đáp án:** Temp table thuộc tempdb, có thể khác database collation. Cột chuỗi khi JOIN có thể xung đột; cân nhắc COLLATE DATABASE_DEFAULT khi phù hợp.

### Bài 27. NFKC có nên áp dụng cho mọi tên người không?

**Đáp án:** Không. NFKC có thể hợp nhất dạng tương thích và làm thay đổi nội dung. Chỉ dùng khi domain yêu cầu và đã kiểm thử.

### Bài 28. Tìm không dấu có nên dùng làm unique key không?

**Đáp án:** Chỉ khi nghiệp vụ muốn các dạng đó là cùng một định danh. Thường nên tách search key và unique key chính xác.

### Bài 29. Test Unicode end-to-end gồm những bước nào?

**Đáp án:** HTTP decoding, Java String, normalization/validation, JDBC binding, DB charset/collation, stored value, ResultSet mapping và response serialization.

### Bài 30. Khi đổi collation, bước nào cần làm trước?

**Đáp án:** Kiểm kê collation/schema, tìm duplicate theo collation đích, kiểm tra index/constraint, thử trên bản sao và backup/restore trước khi triển khai.

## 41. Checklist kiểm thử Unicode và collation

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Encoding | Client, JVM, driver và database thống nhất encoding |
| Supplementary characters | Emoji/code point ngoài BMP round-trip chính xác |
| Normalization | NFC/NFD được giữ hoặc chuẩn hóa theo policy |
| Compatibility normalization | NFKC/NFKD chỉ dùng khi có yêu cầu |
| Case | Kết quả so sánh hoa/thường đúng kỳ vọng |
| Accent | Có phân biệt hay bỏ qua dấu theo từng field |
| Vietnamese đ | Mapping đ/d có được định nghĩa rõ |
| Width/kana | Có cần sensitivity cho ngôn ngữ liên quan |
| Equality | So sánh = phù hợp collation |
| ORDER BY | Thứ tự theo locale và có tie-break |
| LIKE | Pattern và wildcard có hành vi đúng |
| DISTINCT/GROUP BY | Không gộp nhầm dữ liệu |
| JOIN | Cột hai phía có collation tương thích |
| Unique | Collision được kiểm tra trước khi tạo index |
| Index | Expression/collation khớp query |
| Identifier | Quote/folding/case rules đúng DBMS |
| JDBC | setString/setNString và getString/getNString phù hợp |
| HTTP | Request/response không mojibake |
| Migration | Charset/collation thay đổi có backup và plan |
| Multi-DBMS | Test đúng version, driver và collation |

## 42. Kết luận

Kiểm thử Unicode không chỉ là nhìn xem dấu tiếng Việt có hiển thị đúng hay không. Một hệ thống đúng phải bảo toàn dữ liệu qua encoding, hiểu normalization, áp dụng collation phù hợp và xử lý identifier theo quy tắc của từng DBMS.

Các điểm cần ghi nhớ:

- Unicode code point, UTF-16 code unit và grapheme cluster là các đơn vị khác nhau.
- NFC/NFD chuẩn hóa biểu diễn; chúng không tự xóa dấu.
- Chữ đ không được xử lý đầy đủ bằng thuật toán chỉ bỏ combining marks.
- Encoding quyết định cách chuyển byte và ký tự; collation quyết định so sánh/sắp xếp.
- Case-insensitive/accent-insensitive có thể thay đổi equality và unique constraint.
- LIKE, JOIN, GROUP BY, DISTINCT và ORDER BY đều cần test theo collation thực tế.
- Java String dùng UTF-16; JDBC setter phải phù hợp kiểu cột và driver.
- Identifier có dấu có thể được một số DBMS hỗ trợ nhưng làm giảm portability; tên ASCII ổn định thường dễ bảo trì hơn.
- PostgreSQL, MySQL, SQL Server, Oracle và SQLite có charset, collation, identifier và Unicode semantics khác nhau.
- Thay collation hoặc provider version có thể ảnh hưởng index, sort order và khóa duy nhất.

**Khi gỡ lỗi, hãy tách riêng câu hỏi: byte có được giải mã đúng không, chuỗi có được chuẩn hóa đúng không, database so sánh theo collation nào, và parser đang hiểu identifier nào.** Kiểm thử từng lớp bằng fixture tái lập, đúng driver và đúng phiên bản DBMS sẽ giúp phát hiện lỗi Unicode trước khi chúng trở thành sự cố tìm kiếm, đăng nhập, dữ liệu trùng hoặc migration production.
