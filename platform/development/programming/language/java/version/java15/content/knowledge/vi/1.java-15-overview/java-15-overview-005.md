# Đọc Javadoc hiện hành và mốc `Since` của API Java

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Tìm đúng tài liệu API Java SE của phiên bản đang dùng, đi từ module → package → lớp/interface → thành viên.
- Đọc chữ ký phương thức, mô tả hành vi, tham số, giá trị trả về, ngoại lệ, các ghi chú hợp đồng và mục `Since`.
- Phân biệt **phiên bản của trang tài liệu** với **phiên bản đầu tiên API xuất hiện**; quyết định liệu một API có dùng được khi dự án nhắm Java 15 hay không.
- Kiểm tra kết luận bằng `javac --release`, đồng thời nhận ra các cảnh báo về deprecation, API mới hơn và phần còn thiếu trong Javadoc.

Bài tập trung vào **API chuẩn hiện vẫn có trong Java hiện đại**. Java 15 là mốc tương thích để thực hành; không khuyến khích dùng các API đã lỗi thời chỉ vì chúng từng có trong Java 15.

## 2. Hai thông tin phiên bản rất dễ nhầm

Một trang mang tiêu đề `String (Java SE 27 & JDK 27)` mô tả lớp `String` **trong bộ tài liệu JDK 27**. Bên trong trang ấy, phương thức `String.formatted(Object... args)` có nhãn **`Since: 15`**: phương thức đã là một phần của API nền tảng kể từ Java 15 và vẫn được ghi nhận ở JDK 27.

Hãy tách bạch:

| Thông tin | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Phiên bản Javadoc đang mở | Tài liệu này mô tả API của bản Java nào? | Java SE 27 |
| `Since` ở **lớp/interface** | Kiểu này xuất hiện trong API chuẩn từ bản nào? | Xem tại trang khai báo kiểu |
| `Since` ở **phương thức/constructor/field** | Chính thành viên này được thêm từ bản nào? | `String.formatted(...)` → 15 |
| Phiên bản dự án nhắm tới | Mã cần biên dịch/chạy tối thiểu với Java nào? | `--release 15` |
| Trạng thái API | API hiện có còn phù hợp cho mã mới không? | Xem `Deprecated`, ghi chú và release notes |

`Since: 15` **không** có nghĩa “chỉ dùng được trên Java 15”, “bị loại bỏ sau Java 15”, “thay đổi hành vi trong Java 15” hay “được đánh dấu deprecated ở Java 15”. Nó chỉ nêu **mốc xuất hiện của phần tử API được ghi chú**. Với tài liệu chuẩn của nền tảng Java, đây là mốc phiên bản Java SE API; không nhất thiết là ngày một đoạn mã được thêm vào một bản triển khai cụ thể.

## 3. Cách đọc một trang Javadoc hiện hành

1. **Chọn đúng phiên bản tài liệu.** Bắt đầu từ [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/) (bản GA hiện hành ở thời điểm biên soạn, 08/11/2026) hoặc đúng bản JDK mà dự án dùng. Muốn đối chiếu mốc Java 15, mở [Java SE 15 API](https://docs.oracle.com/en/java/javase/15/docs/api/).
2. **Tìm kiểu cần dùng.** Dùng ô Search hoặc điều hướng: module `java.base` → package `java.lang` → class [`String`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html). Với collection, thường tìm trong `java.util`; với stream, tìm `java.util.stream`.
3. **Đọc phần đầu của kiểu.** Xem khai báo `public class`/`interface`, type parameters, các interface/kiểu cha, phần mô tả tổng quát, tính bất biến/điều kiện sử dụng nếu có và `Since` của **kiểu**. Đừng lấy `Since` của kiểu làm mốc cho mọi phương thức bên trong.
4. **Định vị đúng thành viên.** Từ Method Summary/Field Summary/Constructor Summary, chọn **đúng tên và danh sách tham số**. Những overload trùng tên có thể có mốc xuất hiện và hợp đồng khác nhau. Nhấp sang Method Details để đọc đầy đủ.
5. **Đọc hợp đồng trước khi dùng.** Kiểm tra `Parameters`, `Returns`, `Throws`, `Type Parameters`, `API Note`, `Implementation Requirements`/`Implementation Note` và `See Also` khi xuất hiện. Phần mô tả này quan trọng ngang tên phương thức: ví dụ, một API trả về collection có thể quy định không cho phép sửa hoặc không bảo đảm kiểu triển khai.
6. **Tìm `Since` ở đúng cấp.** Trong chi tiết của phương thức, đọc `Since` ngay dưới phương thức đó. Nếu trang chỉ liệt kê thành viên được thừa kế, hãy mở trang **kiểu khai báo thực sự**; nếu không có nhãn `Since`, không được tự gán mốc từ lớp chứa hoặc dựa vào tên gọi.
7. **Đọc trạng thái hiện tại.** Kiểm tra nhãn `Deprecated`, lý do, hướng thay thế, thông tin `forRemoval` nếu có; đối chiếu release notes khi định dùng cho mã mới hoặc nâng cấp JDK. `Deprecated(since="...")` nói về **mốc đánh dấu deprecated**, khác hoàn toàn `@since` nói về **mốc giới thiệu API**.

**Mẹo:** Trang Javadoc của bản mới nhất cho biết API nào đang được tài liệu hóa ở bản đó. Trang của bản mục tiêu và phép biên dịch `--release` mới giúp bạn quyết định chính xác phạm vi tương thích. Một API có `Since` thấp nhưng đã bị gỡ bỏ về sau vẫn không dùng được trên JDK không còn cung cấp nó; vì vậy phải xem cả tính hiện diện và trạng thái ở bản đang xét.

## 4. Ví dụ đối chiếu mốc `Since`

Các API dưới đây đều tồn tại trong Javadoc Java hiện hành; chúng minh họa rằng **mốc thành viên có thể khác mốc kiểu chứa**:

| API | `Since` của API cụ thể | Dùng với đích Java 15? | Kết luận |
| --- | --- | --- | --- |
| `String.isBlank()` | 11 | Có | Kiểm tra chuỗi trống hoặc chỉ gồm ký tự khoảng trắng theo định nghĩa của API |
| `String.formatted(Object... args)` | 15 | Có | Định dạng chuỗi dùng chính chuỗi nhận làm format |
| `Stream.toList()` | 16 | **Không** | Method có trong Javadoc mới nhưng chưa có ở API Java 15 |
| `List.getFirst()` | 21 | **Không** | `List` đã tồn tại từ trước, song phương thức này được thêm về sau |

Tra cứu trực tiếp:
- [`String` trên JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html), tìm `isBlank` và `formatted`.
- [`Stream` trên JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html), tìm `toList`.
- [`List` trên JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html), tìm `getFirst`.

### Trường hợp A: API Java 15 vẫn dùng tốt hôm nay

Lưu chương trình sau thành **`ApiSinceDemo.java`**:

```java
import java.util.List;

public class ApiSinceDemo {
    public static void main(String[] args) {
        String title = "Java %d".formatted(15);
        boolean blank = " \t ".isBlank();
        List<String> labels = List.of("api", "since");

        System.out.println(title);
        System.out.println(blank);
        System.out.println(labels.size());
    }
}
```

Biên dịch với **JDK có hỗ trợ target 15** và chạy trên JDK tương thích:

```bash
javac --release 15 ApiSinceDemo.java
java ApiSinceDemo
```

Kết quả:

```text
Java 15
true
2
```

Giải thích: `List.of` có từ Java 9, `String.isBlank` từ Java 11 và `String.formatted` từ Java 15. Vì cả ba đều nằm trong API của Java 15 và chương trình không sử dụng cú pháp mới hơn mốc đó, nó biên dịch được khi compiler hỗ trợ `--release 15`. Một JDK mới có thể chạy bytecode được tạo cho đích cũ; khi triển khai thực tế vẫn phải xác nhận runtime và các thư viện phụ thuộc.

### Trường hợp B: API có trong Javadoc mới nhưng chưa thuộc Java 15

Mã dưới đây **cố ý không tương thích** với `--release 15`; đây là ví dụ kiểm tra giới hạn, không phải chương trình chạy độc lập:

```java
import java.util.stream.Stream;

class TooNewFor15 {
    static void example() {
        var values = Stream.of("a", "b").toList();
        System.out.println(values);
    }
}
```

`Stream.toList()` mang nhãn `Since: 16`. Vì vậy, dù `javac` đang chạy trên một JDK mới, lệnh `javac --release 15 TooNewFor15.java` sẽ báo không tìm thấy phương thức `toList()` trên `Stream`. Việc máy phát triển cài JDK mới hơn **không tự làm API đó hợp lệ** trong một sản phẩm cam kết tương thích Java 15.

Nếu muốn thu kết quả stream thành danh sách khi nhắm Java 15, có thể dùng API `collect(Collectors.toList())` đã tồn tại trong bản đó; tuy nhiên **không coi hai cách là đồng nhất về mọi bảo đảm** (đặc biệt tính có thể sửa của danh sách). Hãy đọc tài liệu chi tiết của từng cách trước khi thay thế.

## 5. Kiểm chứng tương thích bằng công cụ

`Since` là đầu mối tra cứu, còn `javac --release <phiên_bản>` là phép kiểm tra thực tế cho mã nguồn. Theo tài liệu `javac`, tùy chọn này giới hạn cú pháp/ngôn ngữ, phiên bản class file và **API chuẩn được tài liệu hóa** của phiên bản mục tiêu.

Quy trình cho một ứng dụng phải hỗ trợ Java 15:

1. Xác định **minimum supported Java release** của ứng dụng; với bài này giả sử là 15.
2. Đọc Javadoc bản hiện hành để hiểu hợp đồng API, kiểm tra `Since` tại đúng member và tình trạng deprecation.
3. Đối chiếu với [Javadoc Java 15](https://docs.oracle.com/en/java/javase/15/docs/api/), đặc biệt khi không có nhãn `Since` hoặc cần kiểm tra API có thực sự xuất hiện trong bản mục tiêu.
4. Biên dịch bằng `javac --release 15` với JDK/toolchain có hỗ trợ mức đích này; xem `javac --help` để kiểm tra danh sách release được hỗ trợ.
5. Chạy thử trên một runtime phù hợp với cam kết của dự án và chạy test nghiệp vụ. `--release` chỉ xác nhận phạm vi của **API nền tảng và cú pháp** khi biên dịch; nó không bảo đảm phiên bản thư viện bên thứ ba, cấu hình, môi trường triển khai hoặc mọi hành vi runtime.

**Không thay `--release 15` chỉ bằng `-source 15 -target 15`** rồi mặc định cho rằng đã kiểm soát API. Các tùy chọn source/target chỉ giải quyết một phần vấn đề; khi dùng JDK mới, code vẫn có thể vô tình tham chiếu API chuẩn chưa xuất hiện trong đích cũ nếu không cấu hình platform API tương ứng.

Đọc thêm: [tài liệu `javac` hiện hành](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

## 6. Những bẫy thường gặp khi đọc `Since`

- **Nhìn thấy lớp ở Java 15 rồi suy ra mọi method cũng có:** sai, vì API có thể được mở rộng từng bản; `List.getFirst()` là ví dụ rõ ràng.
- **Đọc mỗi Method Summary:** phần tóm tắt thường không chứa đủ điều kiện, ngoại lệ, hạn chế hoặc `Since`. Mở phần chi tiết member.
- **Nhầm các overload:** `String.format(String, Object...)` và `String.formatted(Object...)` là hai API khác nhau; phải đối chiếu chữ ký chính xác.
- **Mặc định không thấy `Since` nghĩa là “từ Java 1”:** sai. Tài liệu có thể không ghi tag, thành viên được thừa kế hoặc doclet được cấu hình ẩn phần Since. Dùng tài liệu của bản mục tiêu và mã biên dịch để xác nhận.
- **Nhầm mốc thêm API với mốc deprecated:** `@since` khác `@Deprecated(since="...")`; cần đọc cả hai nếu thấy cảnh báo.
- **Chỉ dựa vào bản JDK đang cài trên máy:** JDK mới có API mới, nhưng dự án có thể vẫn nhắm runtime cũ hơn.
- **Coi `Since` của thư viện ngoài là số phiên bản Java:** thư viện có hệ phiên bản riêng. Với thư viện như framework, phải đọc Javadoc, release notes và yêu cầu JDK của **chính thư viện đó**.
- **Bỏ qua phạm vi support:** một API tồn tại không đồng nghĩa mọi bản Java cũ đều còn được nhà cung cấp duy trì. Với ứng dụng mới, chọn runtime đang được hỗ trợ theo chính sách dự án; dùng Java 15 ở đây để học cách tra cứu mốc lịch sử.

## 7. Bài tự kiểm tra

Hãy mở Javadoc hiện hành và tự ghi: **kiểu khai báo → chữ ký chính xác → `Since` của member → minimum Java release của dự án → kết luận**.

1. `String.formatted(Object... args)`: `Since = 15`. Nếu dự án nhắm Java 15, có thể dùng không? **Có**, vì phương thức có từ bản 15 và vẫn tồn tại trong API hiện hành.
2. `Stream.toList()`: `Since = 16`. Nếu dự án nhắm Java 15, có thể dùng trực tiếp không? **Không**; `javac --release 15` sẽ ngăn việc đó.
3. `List.getFirst()`: `Since = 21`. Tại sao `List` xuất hiện trên Java 15 không đủ để kết luận? Vì **mốc thành viên** có thể mới hơn **mốc của interface**.

**Tiêu chí hoàn thành:** Bạn không chỉ tìm ra số `Since`, mà còn xác nhận được API đang tồn tại ở Javadoc đang dùng, đọc đúng hợp đồng của member và kiểm tra tương thích với target release.

## 8. Tài liệu chính thức để dùng lâu dài

- [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/) — tài liệu API hiện hành tại thời điểm biên soạn; khi Java có GA mới, chuyển sang bộ tài liệu đúng phiên bản bạn cần.
- [Java SE 15 API Specification](https://docs.oracle.com/en/java/javase/15/docs/api/) — đối chiếu API của mốc 15, không dùng làm hướng dẫn chọn API lỗi thời.
- [`String` Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html), [`Stream` Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html), [`List` Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html) — ví dụ đọc `Since` theo từng member.
- [Lệnh `javac` Java 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — ý nghĩa và giới hạn của `--release`.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — kiểm tra API/features mới, thay đổi, deprecated hoặc đã bị loại bỏ khi nâng bản Java.