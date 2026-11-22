# Sắp xếp tên tiếng Việt bằng Collator trong Java

## 1. Tình huống thực tế và mục tiêu

Một ứng dụng quản lý học viên, nhân sự hoặc khách hàng có danh sách tên: **Nguyễn Văn An**, **Trần Thị Ánh**, **Phạm Bảo Ân**, **Đặng Thu Đào**, **Đỗ Gia Dũng**, **Võ Quốc Đức**. Người dùng muốn danh sách được sắp xếp một cách hợp lý theo tiếng Việt. Nếu chỉ dùng `String.compareTo()`, các chuỗi được đối chiếu theo thứ tự UTF-16 code units, **không phải quy tắc so sánh chữ cái của ngôn ngữ**. Chữ có dấu, chữ `Đ`, âm chính, dấu thanh, cách viết hoa/thường và tên ghép có thể cho thứ tự khó hiểu.

Java core có `java.text.Collator` để so sánh chuỗi **phù hợp với một locale**, như `vi-VN`. Tuy nhiên, chỉ thay `compareTo` bằng `Collator.compare` chưa đủ cho một tính năng danh bạ hoàn chỉnh: trước hết phải xác định **sắp xếp theo họ hay theo tên gọi**, cách lưu họ/tên đệm/tên chính, cách xử lý nhiều bản ghi tương đương theo collation, và cách giữ kết quả có thể kiểm tra được.

**Bài thực hành này** trình bày từ việc tạo Collator, viết `Comparator` cho dữ liệu có cấu trúc, chạy thử Java 17+, đọc kết quả, cho đến những lỗi dữ liệu Unicode và cách kiểm thử trong sản phẩm thật.

### Sau bài học bạn sẽ làm được gì?

1. Tạo `Collator` với `Locale.forLanguageTag("vi-VN")` và giải thích vì sao nó khác `String.compareTo`.
2. Chọn `Collator.``PRIMARY`/`SECONDARY`/`TERTIARY`/`IDENTICAL` và `CANONICAL_DECOMPOSITION` phù hợp với nhu cầu.
3. Sắp xếp một danh sách theo **tên gọi**, sau đó theo họ, tên đệm và mã ID — hoặc đổi chính sách để sắp xếp **theo họ**.
4. Viết chương trình Java 17+ độc lập, có lệnh biên dịch và đầu ra kiểm chứng được.
5. Phân biệt **tương đương theo Collator** với `String.equals` và danh tính người trong database.
6. Không làm mất người hoặc ghi đè dữ liệu khi dùng `TreeSet`/`TreeMap` với comparator không nhất quán với equals.
7. Nhận diện vấn đề chuẩn hóa Unicode (dựng sẵn so với tổ hợp), whitespace, trường hợp tên ghép, các độ mạnh so sánh và dữ liệu nguồn.
8. Thiết kế bộ test đủ các lớp tên tiếng Việt và kiểm soát thay đổi khi nâng JDK/CLDR.

## 2. “Sắp xếp tên tiếng Việt” là yêu cầu nghiệp vụ cần xác định

Không có một phép `sort` duy nhất luôn đúng cho mọi danh sách người Việt. Tối thiểu phải chọn rõ một trong hai cách:

- **Sắp xếp theo họ, rồi tên đệm, rồi tên gọi:** hữu ích cho một số danh mục hồ sơ hoặc bản in theo họ. Ví dụ các tên mang họ Bùi, Đặng, Đỗ, Hồ, Lê, Nguyễn, Phạm, Trần, Võ được nhóm theo trường họ và thứ tự collation.
- **Sắp xếp theo tên gọi, sau đó phân giải trùng:** thường gặp ở danh sách lớp hoặc danh bạ tiếng Việt, nơi “An”, “Anh”, “Ánh”, “Bình”, “Dung”, “Dũng”, “Đào”, “Đức” được tra cứu bằng tên gọi. Dù vậy, cách sắp xếp theo trường tên gọi là **quy ước của sản phẩm**, không phải điều Collator tự biết từ họ tên đầy đủ.

Một chính sách dữ liệu rõ ràng có thể là:

```text
Sort by:
  1. givenName (theo Collator vi-VN)
  2. familyName (theo Collator vi-VN)
  3. middleName (theo Collator vi-VN)
  4. immutable person ID (thứ tự số, để có kết quả quyết định)
```

Nếu sản phẩm cần nhóm họ trước, thay thứ tự các khóa so sánh. Quan trọng là **không suy đoán quy tắc** chỉ từ việc chuỗi có dấu tiếng Việt.

### Họ tên không phải lúc nào cũng tách bằng từ cuối

`"Nguyễn Thị Minh Anh"` có thể có tên gọi ghép `"Minh Anh"`. Những tên như `"Thị Hồng"` hoặc cấu trúc đặt tên đặc biệt, tên quốc tế, tên chỉ có một từ, dữ liệu thiếu tên đệm cũng cần chính sách. Vì vậy, không nên mặc định:

```java
String givenName =
        fullName.substring(fullName.lastIndexOf(' ') + 1);
```

Đây là **mẫu dễ sai có chủ ý**, không phải parser tên tiếng Việt đáng tin. Nó luôn lấy **từ cuối**, không nhất thiết là trường tên gọi mà người dùng xác nhận.

**Thiết kế phù hợp hơn:** thu thập/lưu các trường `familyName`, `middleName`, `givenName` hoặc một cấu trúc tên đã được chuẩn hóa theo nghiệp vụ. Có thể có thêm `displayName` giữ chính xác cách người dùng muốn hiển thị và `sortName` do người dùng/nhân sự xác nhận nếu danh mục phức tạp.

## 3. Collator là gì và khác String.compareTo như thế nào?

`java.text.Collator` là một `Comparator<Object>` có khả năng so sánh văn bản theo dữ liệu/ngữ cảnh ngôn ngữ. Với `String`, ta dùng:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vietnamese);

int result = collator.compare("Dung", "Đung");
```

Đoạn này nằm trong phương thức Java, cần import `java.text.Collator` và `java.util.Locale`. Kết quả âm/0/dương cho biết thứ tự tương đối theo Collator được cài trên runtime.

So sánh với:

```java
int natural = "Dung".compareTo("Đung");
```

`String.compareTo` so theo các UTF-16 code units; nó không hiểu thứ tự chữ cái tiếng Việt, dấu thanh hoặc các mức khác biệt ngôn ngữ. Chỉ vì một ký tự có code point lớn hơn không có nghĩa nó phải đứng sau mọi chữ cái khác khi sắp xếp cho người đọc Việt.

**Chú ý:** Collator có thể phụ thuộc bản JDK, nguồn dữ liệu locale và cấu hình provider. Kết quả cụ thể của những cặp chữ có dấu cần được kiểm thử trên phiên bản Java triển khai; không viết luật thủ công kiểu “mọi dấu sắc luôn xếp sau mọi dấu huyền” rồi khẳng định đó là hợp đồng của API.

### Khởi tạo locale tường minh

Nên viết:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(vi);
```

thay vì `Collator.getInstance()` nếu dữ liệu đang được sắp xếp theo tiếng Việt. Factory không có tham số dùng locale mặc định của JVM, có thể khác giữa máy phát triển, CI và server.

Không đổi `Locale.setDefault(...)` cho từng request chỉ để sort. Đây là global state ảnh hưởng các luồng khác. Hãy truyền locale và giữ rõ phạm vi comparator.

### Collator không sửa tên

`collator.compare(a,b)` trả kết quả so sánh; nó không trả một chuỗi “đã chuẩn hóa” và không tự biến đổi `a`, `b` trong database. Các thao tác như đổi hoa/thường, NFC, loại bỏ khoảng trắng thừa hay tách phần họ-tên thuộc **những chính sách dữ liệu riêng**, không phải side effect của `compare`.

## 4. Chọn strength: khác biệt nào có ảnh hưởng đến thứ tự?

`Collator` hỗ trợ các mức strength:

| Mức | Ý nghĩa khái quát | Khi nào cân nhắc |
| --- | --- | --- |
| `Collator.PRIMARY` | Phân biệt trọng số nền tảng; nhiều khác biệt viết hoa hoặc dấu thanh có thể bị xem nhẹ, tùy locale. | Nhóm kết quả tìm kiếm rất mềm dẻo, **không mặc định là identity**. |
| `Collator.SECONDARY` | Xét thêm khác biệt thứ cấp, thường liên quan dấu/biến thể ký tự. | Khi cần phân biệt nhiều dạng có dấu hơn PRIMARY. |
| `Collator.TERTIARY` | Xét thêm khác biệt cấp ba, thường có case. | Một mức thông dụng cho sort hiển thị phân biệt hơn; vẫn phải kiểm thử. |
| `Collator.IDENTICAL` | Mức phân biệt mạnh nhất theo implementation. | Khi cần phân biệt sâu hơn trong collation, nhưng không tự suy ra nhất quán với `String.equals`. |

Ánh xạ cụ thể từ dấu tiếng Việt sang các cấp trọng số **phụ thuộc dữ liệu collation**. Một số dấu cấu thành chữ cái khác biệt theo thứ tự gốc; các dấu thanh có thể là trọng số khác. Đừng phát biểu mọi dấu tiếng Việt luôn thuộc đúng một cấp như nhau ở mọi JDK/provider.

### Lựa chọn cho bài thực hành

Ví dụ dùng:

```java
Collator vi = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
vi.setStrength(Collator.TERTIARY);
vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
```

Mức `TERTIARY` giúp minh họa sort có phân biệt case/dấu theo dữ liệu runtime; `CANONICAL_DECOMPOSITION` hỗ trợ các dạng Unicode dựng sẵn và tổ hợp theo quy tắc chuẩn tắc.

Nếu sản phẩm là ô tìm kiếm “không phân biệt hoa/thường, ít phân biệt dấu”, có thể cần một comparator khác hoặc một search index riêng, **không nhất thiết dùng cùng comparator để xác định danh tính dữ liệu**.

### Thử trực tiếp các mức strength

```java
Collator primary = (Collator) vi.clone();
primary.setStrength(Collator.PRIMARY);

int p = primary.compare("An", "an");
int t = vi.compare("An", "an");
```

Với runtime được dùng để kiểm tra bài này, `p == 0` còn `t != 0`. Nhưng hãy đặt test trên JDK mục tiêu thay vì lấy một cặp làm bằng chứng cho toàn bộ bảng chữ cái tiếng Việt.

### Không sửa Collator đã được dùng làm comparator của cây

`Collator` là đối tượng có thể cấu hình lại bằng `setStrength`, `setDecomposition`. Nếu bạn đã dùng nó để xây `TreeSet`/`TreeMap` chứa dữ liệu, **không đổi luật so sánh giữa chừng**, vì cấu trúc cây không tự xây lại theo luật mới. Hãy tạo/clone một Collator khác hoặc dựng collection mới từ dữ liệu nguồn khi thay chính sách.

## 5. Unicode dựng sẵn và dấu tổ hợp

Nhiều chữ tiếng Việt có thể được biểu diễn bằng các dãy code point khác nhau. Ví dụ `á`:

```text
Dạng dựng sẵn:    U+00E1
Dạng tổ hợp:      U+0061 U+0301
```

Với Java:

```java
String precomposed = "\u00E1";
String decomposed = "a\u0301";

System.out.println(precomposed.equals(decomposed));
// false: dãy UTF-16 khác nhau.
```

Hai chuỗi có thể trông giống nhau, nhưng `String.equals` so sánh dữ liệu code unit. Khi dùng `Collator` có `CANONICAL_DECOMPOSITION`, ví dụ Java của bài cho kết quả `compare(precomposed,decomposed)==0` trên runtime kiểm thử.

**Không nhầm hai việc:**

- `Collator` so sánh hai chuỗi theo quan hệ collation đã chọn.
- `Normalizer.normalize(text, Normalizer.Form.NFC)` thay đổi cách biểu diễn của **một chuỗi** sang dạng chuẩn hóa khi thích hợp.

Một ứng dụng có thể chọn chuẩn hóa tên lúc nhập để dễ tìm, nhưng cần quyết định rõ: giữ nguyên spelling nguồn hay không, sửa dữ liệu cũ thế nào, và cần giữ lịch sử/audit hay không. **NFC không phải loại bỏ dấu**; nó không biến `Nguyễn` thành `Nguyen`.

### Nguy cơ so sánh tên có Unicode khác nhau

Nếu dữ liệu nhập từ nhiều nền tảng, một tên có thể chứa:

- Unicode dựng sẵn hoặc các ký tự tổ hợp.
- Non-breaking space hoặc khoảng trắng đặc biệt.
- Chữ hoa/thường không đồng đều.
- Dấu câu trong tên, gạch nối, apostrophe.
- Ký tự zero-width, ký tự không nhìn thấy.
- Tên có ký tự chữ viết khác như Latin, Han hoặc Arabic.

Đừng áp `replaceAll("[^a-zA-Z]","")` để “làm sạch” họ tên tiếng Việt — phép này xóa hoặc biến dạng ký tự hợp lệ. Nếu muốn chính sách chuẩn hóa khoảng trắng hoặc kiểm soát ký tự lạ, hãy viết validation/test riêng, giải thích cho người dùng và tránh âm thầm làm mất thông tin.

## 6. Mô hình dữ liệu: lưu họ, đệm, tên và ID riêng

Dùng `record` Java 17 cho ví dụ:

```java
record Person(int id, String family,
              String middle, String given) {}
```

Ở đây:

- `id` là định danh của một người trong tập dữ liệu mẫu, giữ nguyên dù đổi tên.
- `family` là họ như `Nguyễn`, `Trần`, `Lê`, `Đặng`.
- `middle` là thành phần tên đệm đã được dữ liệu xác nhận.
- `given` là tên gọi đã được dữ liệu xác nhận; có thể nhiều từ nếu hợp đồng cho phép.
- Thứ tự các trường lưu không bắt buộc chính là thứ tự sort của UI.

**Record không tự xử lý tên người.** Mỗi field phải được tạo đúng từ form hoặc nguồn dữ liệu đáng tin; không suy ra chắc chắn từ cách tách string trắng.

Nếu nghiệp vụ cần full name:

```java
String fullName = String.join(
        " ", person.family(), person.middle(), person.given());
```

Đây chỉ là một ví dụ trong phương thức khi cả ba trường đều có giá trị thích hợp. Sản phẩm thật cần quy tắc cho tên đệm rỗng, quốc gia khác, viết hoa/honorific và cách hiển thị từng locale. **Tên gọi để sort và tên đầy đủ để hiển thị là hai nhu cầu khác nhau.**

### Vì sao có mã ID trong comparator?

Khi hai người đều có `given="An"` và cùng họ/tên đệm gần giống, sort theo tên có thể trả 0. Để danh sách có thứ tự **quyết định** ngay cả khi trường tên trùng theo Collator, có thể thêm ID làm tie-breaker cuối.

Tuy nhiên, record có `equals` dựa trên **tất cả component**. Comparator tên + ID **không tự chứng minh nhất quán với record.equals** cho mọi đối tượng nếu hai record trùng ID nhưng trường tên khác nhau mà collation coi bằng nhau. Vì thế chương trình dùng comparator cho **`List.sort`**, không dùng nó làm danh tính của `TreeSet<Person>`.

Trong sản phẩm, giữ danh tính ở `Map<Integer, Person>` theo ID (hoặc bảng có primary key), và dùng bản sao `List<Person>` cho hiển thị.

## 7. Comparator cho hai cách sắp xếp thông dụng

### 7.1. Theo tên gọi trước

```java
Comparator<String> viText = collator::compare;

Comparator<Person> byGiven =
        Comparator.comparing(Person::given, viText)
                .thenComparing(Person::family, viText)
                .thenComparing(Person::middle, viText)
                .thenComparingInt(Person::id);
```

Đây là đoạn Java trong một phương thức có biến `collator` đã được khởi tạo và record `Person` đã định nghĩa.

Luồng so sánh:

1. So `given` theo quy tắc tiếng Việt.
2. Nếu cùng nhóm collation, so tiếp `family`.
3. Nếu vẫn tương đương, so tiếp `middle`.
4. Nếu vẫn tương đương, so `id` số nguyên.

Không cần tự viết `if/else` phức tạp và không dùng `compareTo` của toàn bộ họ tên làm khóa duy nhất.

### 7.2. Theo họ trước

```java
Comparator<Person> byFamily =
        Comparator.comparing(Person::family, viText)
                .thenComparing(Person::middle, viText)
                .thenComparing(Person::given, viText)
                .thenComparingInt(Person::id);
```

Chỉ đổi thứ tự field là có **quy ước sắp xếp khác**. Hai comparator đều dùng dữ liệu collation tiếng Việt nhưng trả danh sách khác nhau. Đây là bằng chứng quan trọng rằng **Collator không tự quyết định “sắp theo họ hay tên”**.

### 7.3. So sánh với natural String order

```java
Comparator<Person> byUnicode =
        Comparator.comparing(Person::given)
                .thenComparingInt(Person::id);
```

Đoạn này dùng thứ tự `String.compareTo`, không phải locale-specific collation. Nó hữu ích làm đối chứng khi test, nhưng không nên coi thứ tự Unicode natural là tương đương thứ tự đọc tên tiếng Việt.

### 7.4. Dùng List.sort thay vì biến danh bạ thành TreeSet

`List.sort(comparator)` **chỉ thay đổi thứ tự phần tử**, không tự xóa phần tử khi comparator trả 0. `TreeSet` và `TreeMap` lại coi `compare==0` là trùng, có thể mất bản ghi.

Ví dụ một nhóm tên tương đương dưới một Collator mềm:

```java
Collator primary = (Collator) collator.clone();
primary.setStrength(Collator.PRIMARY);

TreeSet<String> names = new TreeSet<>(primary);
names.add("An");
names.add("an");
// Có thể chỉ còn một phần tử nếu compare("An","an")==0.
```

Trong demo runtime đã kiểm tra, `TreeSet` này có size `1`; còn `HashSet<String>` chứa cả hai tên (size `2`) vì `String.equals` phân biệt case. Nếu phải bảo toàn từng người, dùng ID làm identity rồi sort một `List`.

## 8. Chương trình Java 17+ độc lập: sắp xếp 12 tên tiếng Việt

Tạo file **`VietnameseNameSortDemo.java`** bằng UTF-8. Ví dụ cố tình **in danh sách ID** chứ không in trực tiếp chữ có dấu trong stdout kiểm tra, để tránh nhầm lỗi font/encoding của terminal với lỗi thuật toán sắp xếp. Dữ liệu `family`, `middle`, `given` vẫn là chuỗi tiếng Việt thực tế trong code.

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

public class VietnameseNameSortDemo {

    record Person(int id, String family,
                  String middle, String given) {}

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Collator language = Collator.getInstance(vi);
        language.setStrength(Collator.TERTIARY);
        language.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        Comparator<String> viText = language::compare;

        List<Person> people = List.of(
                new Person(101, "Nguyễn", "Văn", "An"),
                new Person(102, "Trần", "Thị", "Ánh"),
                new Person(103, "Lê", "Minh", "Anh"),
                new Person(104, "Phạm", "Bảo", "Ân"),
                new Person(105, "Đặng", "Thu", "Đào"),
                new Person(106, "Đỗ", "Gia", "Dũng"),
                new Person(107, "Nguyễn", "Ngọc", "Dung"),
                new Person(108, "Hồ", "Thị", "Hòa"),
                new Person(109, "Bùi", "Minh", "Bình"),
                new Person(110, "Võ", "Quốc", "Đức"),
                new Person(111, "Nguyễn", "Thị", "Anh"),
                new Person(112, "Nguyễn", "Thị", "An")
        );

        Comparator<Person> byGiven =
                Comparator.comparing(Person::given, viText)
                        .thenComparing(Person::family, viText)
                        .thenComparing(Person::middle, viText)
                        .thenComparingInt(Person::id);

        List<Person> givenSorted = new ArrayList<>(people);
        givenSorted.sort(byGiven);
        System.out.println("givenIds="
                + givenSorted.stream().map(Person::id).toList());

        Comparator<Person> byFamily =
                Comparator.comparing(Person::family, viText)
                        .thenComparing(Person::middle, viText)
                        .thenComparing(Person::given, viText)
                        .thenComparingInt(Person::id);

        List<Person> familySorted = new ArrayList<>(people);
        familySorted.sort(byFamily);
        System.out.println("familyIds="
                + familySorted.stream().map(Person::id).toList());

        List<Person> natural = new ArrayList<>(people);
        natural.sort(Comparator.comparing(Person::given)
                .thenComparingInt(Person::id));
        System.out.println("naturalIds="
                + natural.stream().map(Person::id).toList());

        String composed = "\u00E1";
        String decomposed = "a\u0301";
        System.out.println("utf16Equals="
                + composed.equals(decomposed));
        System.out.println("collatorEquivalent="
                + (language.compare(composed, decomposed) == 0));

        Collator primary = (Collator) language.clone();
        primary.setStrength(Collator.PRIMARY);

        System.out.println("primaryCaseEquivalent="
                + (primary.compare("An", "an") == 0));
        System.out.println("tertiaryDistinguishesCase="
                + (language.compare("An", "an") != 0));

        TreeSet<String> tree = new TreeSet<>(primary);
        tree.add("An");
        tree.add("an");

        System.out.println("treePrimarySize=" + tree.size());
        System.out.println("hashSetSize="
                + new HashSet<>(
                        List.of("An", "an")).size());
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn trong thư mục chứa file:

```bash
javac -encoding UTF-8 VietnameseNameSortDemo.java
java VietnameseNameSortDemo
```

**Stdout đã kiểm tra bằng JShell trên môi trường OpenJDK hiện có, với Collator được cấu hình như ví dụ:**

```text
givenIds=[112, 101, 103, 111, 102, 104, 109, 107, 106, 105, 110, 108]
familyIds=[109, 105, 106, 108, 103, 107, 112, 111, 101, 104, 102, 110]
naturalIds=[101, 112, 103, 111, 109, 107, 106, 108, 102, 104, 105, 110]
utf16Equals=false
collatorEquivalent=true
primaryCaseEquivalent=true
tertiaryDistinguishesCase=true
treePrimarySize=1
hashSetSize=2
```

**Phạm vi của stdout:** ba danh sách ID là kết quả thực nghiệm từ môi trường Java có locale data tương ứng. Thứ tự những tên có dấu có thể thay đổi theo JDK/vendor/locale provider và thuật toán collation được tích hợp. Code chạy theo Java 17+, nhưng khi cần snapshot test chính xác toàn bộ ID trên một JDK khác, hãy xác nhận dữ liệu collation và môi trường build/deploy. Những invariant quan trọng như `List.sort` không làm mất record, hoặc `String.equals` của hai dạng Unicode khác nhau là false, có ý nghĩa độc lập hơn với phiên bản runtime.

### Bảng tra ID để đọc kết quả

| ID | Họ | Đệm | Tên gọi |
| ---: | --- | --- | --- |
| 101 | Nguyễn | Văn | An |
| 102 | Trần | Thị | Ánh |
| 103 | Lê | Minh | Anh |
| 104 | Phạm | Bảo | Ân |
| 105 | Đặng | Thu | Đào |
| 106 | Đỗ | Gia | Dũng |
| 107 | Nguyễn | Ngọc | Dung |
| 108 | Hồ | Thị | Hòa |
| 109 | Bùi | Minh | Bình |
| 110 | Võ | Quốc | Đức |
| 111 | Nguyễn | Thị | Anh |
| 112 | Nguyễn | Thị | An |

### Giải thích từng dòng output

- `givenIds`: dùng **tên gọi trước**; nếu tương đương thì đối chiếu thêm họ, đệm, ID. Cặp cùng tên `An` (101 và 112) có thể được phân giải dựa vào họ/đệm thay vì giữ nguyên thứ tự nhập.
- `familyIds`: cùng Collator nhưng dùng **họ trước**, nên nhóm ID và thứ tự khác đáng kể.
- `naturalIds`: dùng `String.compareTo` cho tên gọi, cho thứ tự khác do xét code units thay vì collation tiếng Việt.
- `utf16Equals=false`: `á` dựng sẵn và `a + dấu sắc` là hai chuỗi UTF-16 khác nhau.
- `collatorEquivalent=true`: với `CANONICAL_DECOMPOSITION`, Collator của runtime coi hai dạng ấy tương đương.
- `primaryCaseEquivalent=true` và `tertiaryDistinguishesCase=true`: các mức strength cho quan hệ so sánh khác nhau giữa `An` và `an` trong runtime thử.
- `treePrimarySize=1`: một TreeSet ở PRIMARY gộp hai spelling theo comparator; `hashSetSize=2`: HashSet giữ cả hai theo `String.equals`.

**Ví dụ không thay đổi JVM default locale, không đọc tệp nguồn khác, không gọi mạng và không ghi database.** Nó dùng hai bản copy riêng để tránh một phép sort ảnh hưởng đầu vào cho phép sort sau.

## 9. Muốn hiển thị tên thay vì ID thì làm thế nào?

Trong ứng dụng thực, bạn có thể hiển thị danh sách sau sort bằng một phương thức:

```java
for (Person p : givenSorted) {
    System.out.println(
            p.family() + " " + p.middle() + " " + p.given());
}
```

Đây là **đoạn code trong phương thức** đang có `givenSorted`; không phải chương trình độc lập. Khi terminal dùng UTF-8 và font hỗ trợ, các tên tiếng Việt sẽ được hiển thị. Nếu output thành dấu hỏi hoặc ô vuông, hãy kiểm tra **console encoding, byte stream và font** trước khi quy lỗi cho Collator.

Để dữ liệu giữ nghĩa:

- File mã nguồn cần được lưu UTF-8; `javac -encoding UTF-8` khai báo charset của file nguồn.
- `System.out` và terminal cần cấu hình phù hợp để nhìn thấy glyph.
- Hệ thống ghi log/CSV cần encoding tường minh và font/reader phù hợp.
- `Collator` làm nhiệm vụ **so sánh**, không sửa encoding hoặc tự chèn Unicode normalization vào String.

Không tự loại dấu khi xuất file chỉ để tránh vấn đề console; đó là **mất dữ liệu tên riêng**.

## 10. Tránh lỗi mất người khi dùng TreeSet/TreeMap

Tương đương theo `Collator.compare(a,b)==0` **không nhất thiết giống bằng nhau theo `String.equals`**. Với `TreeSet`/`TreeMap`, comparator quyết định khóa nào trùng.

Ví dụ:

```java
Collator primary = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
primary.setStrength(Collator.PRIMARY);

TreeSet<String> set = new TreeSet<>(primary);
set.add("An");
set.add("an");
```

Nếu primary comparator cho hai chuỗi bằng nhau, `set.size()` chỉ là 1 dù `"An".equals("an")` là false.

Đây là **hành vi theo contract của TreeSet**, không phải lỗi runtime. Nhưng nếu cả hai tên thuộc hai người khác nhau thì dùng `TreeSet` như nguồn dữ liệu duy nhất sẽ làm mất một người.

### Cách làm rõ trách nhiệm

- **Dữ liệu gốc:** `Map<Integer, Person>` hoặc database theo ID.
- **UI sắp xếp:** `List<Person>` + `sort`.
- **Tìm kiếm mềm theo tên:** search index hoặc `Collator` cấu hình theo yêu cầu tìm kiếm.
- **Danh tính:** ID hoặc quy tắc entity equality của sản phẩm, không phải tên hiển thị.
- **Thứ tự quyết định:** comparator có tie-break phù hợp.

Nếu thật sự cần `TreeSet<String>` để vừa sort theo ngôn ngữ vừa giữ mọi spelling khác nhau theo `String.equals`, có thể thêm natural-order tie-break:

```java
Comparator<String> safeOrder =
        ((Comparator<String>) primary::compare)
                .thenComparing(Comparator.naturalOrder());

TreeSet<String> distinct = new TreeSet<>(safeOrder);
```

Khi Collator trả 0, `String.compareTo` phân biệt các String khác nhau; điều này tạo comparator nhất quán với `String.equals` khi các thành phần tuân thủ hợp đồng và không đổi. Nhưng đây chỉ là giải pháp cho **`String` identity**. Đối với `Person`, phải xét đúng định nghĩa `equals` của kiểu đối tượng; ID tie-break có thể phù hợp trong List sort mà chưa đủ cho TreeSet chứa record có equals dựa trên cả bốn field.

### Đừng thay comparator sau khi đưa vào cây

`Collator` là mutable. Đổi `setStrength` từ TERTIARY sang PRIMARY sau khi TreeSet đã có phần tử có thể làm cấu trúc cây không còn tương thích với thứ tự mới. Không mutate Collator đang được dùng làm comparator của collection có dữ liệu; tạo bản mới và dựng lại collection từ bản gốc khi đổi chính sách.

## 11. Tối ưu sort: CollationKey khi nhiều lần so sánh cùng một tên

`Collator.compare(a,b)` có thể phải tính trọng số collation mỗi lần. Khi sort rất nhiều tên hoặc lặp nhiều lần trên cùng dữ liệu, `CollationKey` có thể giúp giảm công việc lặp:

```java
Collator vi = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
vi.setStrength(Collator.TERTIARY);
vi.setDecomposition(Collator.CANONICAL_DECOMPOSITION);

CollationKey a = vi.getCollationKey("Nguyễn");
CollationKey b = vi.getCollationKey("Trần");
int comparison = a.compareTo(b);
```

Đây là đoạn Java trong phương thức, cần import `java.text.CollationKey` và `java.text.Collator`. Key được tạo theo **cùng Collator và cùng configuration** để so sánh. Nó không phải một ID Unicode chung hay một khóa lưu lâu dài cho mọi phiên bản JDK.

### Cách cache hợp lý

Nếu danh sách lớn và tính toán nhiều lần:

1. Quy định locale và strength/decomposition **trước khi** tạo key.
2. Tạo `CollationKey` cho từng trường cần sort khi load hoặc xây view model.
3. Cache theo một khóa thể hiện **version của dữ liệu tên và cấu hình comparator**.
4. Khi tên hoặc locale/config thay đổi, vô hiệu hóa cache và tạo lại key.
5. Chỉ so key tạo bởi Collator có cùng cấu hình; không coi byte `toByteArray()` là protocol bền vững giữa JDK/CLDR versions.

`CollationKey` là tối ưu cần benchmark. Với vài chục/hàng trăm tên, một comparator dùng Collator trực tiếp thường đơn giản hơn và đủ nhanh. Không tối ưu sớm rồi làm cache sai trong một danh sách tên thường xuyên được cập nhật.

## 12. Null, chuỗi trống, tên ghép và dấu câu

Dữ liệu thực không đẹp như mười hai record của bài. Trước khi dùng Comparator, quyết định:

### 12.1. Tên null

`Collator.compare` không được thiết kế để nhận null như một tên hợp lệ. Có hai lựa chọn rõ ràng:

- Validation ở tầng nhập: yêu cầu trường tên không null, không rỗng theo nghiệp vụ.
- Nếu domain cho phép thiếu tên, dùng comparator xử lý null tường minh như `Comparator.nullsLast(viText)`, nhưng phải test và quyết định cách hiển thị “chưa có tên”.

Ví dụ minh họa:

```java
Comparator<String> optionalName =
        Comparator.nullsLast(viText);
```

Cú pháp chỉ hợp lý khi `viText` là comparator dùng cho String được tạo trước đó. **Không tự biến null thành chuỗi rỗng** rồi xem đây là họ tên thật nếu sản phẩm cần phân biệt hai trạng thái.

### 12.2. Chuỗi rỗng và whitespace

`""`, `" "`, `"Nguyễn  Văn"`, `"Nguyễn\u00A0Văn"` có thể đến từ những nguồn khác nhau. Nếu sản phẩm muốn gom các khoảng trắng thừa, thực hiện ở bước **validation/normalization đã định nghĩa**, không hy vọng Collator tự giải quyết mọi loại whitespace Unicode.

`String.trim()`, `strip()` và regex `\\s+` có giới hạn về lớp whitespace và không nhất thiết xử lý toàn bộ Unicode spacing giống nhau. Nếu yêu cầu đặc biệt, dùng chính sách dựa trên code point và test NBSP/thin spaces; quan trọng nhất là **không làm mất tên gốc** khi xử lý dữ liệu có giá trị pháp lý.

### 12.3. Tên ghép

Một người có thể được gọi bằng tên hai từ, ví dụ `"Minh Anh"`. Nếu cấu trúc `given` chứa hai từ thì Collator so sánh cả cụm. Không chỉ lấy từ cuối rồi làm thay đổi tên gọi người dùng đã xác nhận. Nếu sản phẩm cần sort theo từ cuối, đó là một **chính sách mới** cần được mô tả riêng, không tự suy từ cách dùng Collator.

### 12.4. Số và mã lẫn trong tên

Các nhãn như `"Lớp 2"` và `"Lớp 10"` không nhất thiết được so theo số học bằng Collator văn bản thông thường. Nếu có hậu tố số dùng làm dữ liệu nghiệp vụ, nên tách trường số rồi dùng comparator kiểu số. Không tự tách chữ số trong họ tên nếu schema không quy định.

### 12.5. Không loại bỏ chữ Đ hoặc dấu thanh

Một số cách “sửa tiếng Việt” bằng `toLowerCase(Locale.ROOT)` cộng loại dấu có thể khiến `D`/`Đ` hoặc các nguyên âm khác bị gộp sai theo mong đợi người dùng. **Đừng thay bộ quy tắc Collator bằng một bảng thay thế dấu thủ công** khi chưa có tài liệu văn hóa/nghiệp vụ, test đầy đủ và chính sách tương thích.

## 13. Kiểm thử locale provider và phiên bản JDK

`Collator.getInstance(Locale.forLanguageTag("vi-VN"))` trả một instance từ locale service của runtime. Có thể kiểm tra locale khả dụng bằng:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
boolean listed = java.util.Arrays.stream(
        Collator.getAvailableLocales())
        .anyMatch(vi::equals);
```

Đoạn này nằm trong phương thức Java, cần import `java.util.Arrays` nếu dùng tên ngắn. `getAvailableLocales()` cho biết runtime công bố các locale có sẵn qua API, **không phải giấy chứng nhận mọi dữ liệu collation tiếng Việt đã được kiểm tra đúng mong đợi sản phẩm**.

Nếu locale không có implementation/data cụ thể, Java có thể áp cơ chế fallback; đừng suy rằng factory nhất định ném exception để báo “không hỗ trợ”. Khi QA, test những cặp tên tiếng Việt mà sản phẩm xem quan trọng, và ghi Java vendor/version.

### java.locale.providers

Thứ tự nguồn locale có thể được cấu hình lúc khởi động JVM, ví dụ:

```bash
java -Djava.locale.providers=CLDR VietnameseNameSortDemo
```

Tùy JDK và dịch vụ, `Collator` có thể dùng implementation/dữ liệu không giống provider của `NumberFormat` hay `DateFormat`. Một số dữ liệu collation có ngoại lệ giữa CLDR và legacy providers; không khẳng định đặt `CLDR` khiến mọi API cùng dùng một thuật toán CLDR cụ thể. Ngoài ra, dữ liệu locale của JDK có thể thay đổi theo phiên bản.

**Quy tắc vận hành:** nếu kết quả sort có ý nghĩa pháp lý hoặc thứ tự báo cáo cần tái lập chính xác lâu dài, kiểm soát runtime, dữ liệu/nguyên tắc so sánh và regression tests; đừng lưu binary collation keys rồi giả định vẫn tương thích sau mọi nâng cấp.

### Kiểm thử nhiều ngôn ngữ

Nếu một danh sách có cả tên tiếng Việt và tên quốc tế, cần chính sách cho:

- Người mang tên có ký tự không thuộc tiếng Việt, chữ Latin mở rộng, dấu phụ lạ.
- Tên Hán, Nhật, Hàn, Arabic hoặc chữ viết khác.
- Tên nhiều thành phần, không có họ, thứ tự tên khác văn hóa.
- Người dùng chọn giao diện tiếng Anh nhưng dữ liệu là tên tiếng Việt — **locale của nội dung và locale UI không nhất thiết trùng nhau**.

Có thể chọn `vi-VN` để sắp xếp một danh mục được xác định là danh sách tên Việt ngay cả khi UI hiện tiếng Anh; hoặc cho phép tùy chọn thứ tự sort theo locale người xem. Cần trình bày rõ lựa chọn, vì hai người dùng có thể thấy thứ tự khác nếu sản phẩm cố tình sort theo locale riêng.

## 14. Các lỗi thường gặp và cách xử lý

| Sai lầm | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `String.compareTo` và nghĩ là thứ tự chữ cái tiếng Việt | So sánh theo UTF-16 code units. | Dùng Collator vi-VN và test đúng locale. |
| Chỉ dùng `Collator.getInstance()` | Phụ thuộc locale mặc định JVM. | Truyền `Locale.forLanguageTag("vi-VN")`. |
| Sắp xếp full name nhưng nghiệp vụ muốn theo tên gọi | Chuỗi bắt đầu bằng họ; Collator không tự tách tên. | Lưu field given/family/middle; sort đúng khóa. |
| Lấy từ cuối làm tên gọi cho mọi người | Tên ghép và dữ liệu đa văn hóa bị xử lý sai. | Thu thập/kiểm tra thành phần tên theo domain. |
| Xóa dấu để sắp xếp cho dễ | Có thể thay đổi/đánh mất identity tên. | Dùng collation; phân biệt sort với normalization. |
| Đổi `setStrength` khi TreeSet đang dùng Collator | Cây không rebuild theo thứ tự mới. | Tạo comparator/collection mới. |
| Dùng `TreeSet` làm danh sách người độc nhất theo Collator | `compare==0` có thể gộp hai người khác nhau. | Lưu theo ID, sort List. |
| Tie-break bằng một trường không duy nhất | Các bản ghi khác nhau vẫn có thể compare==0. | Thêm ID ổn định để thứ tự List quyết định; định nghĩa equals riêng cho Set. |
| Dùng Collator strength PRIMARY cho mọi mục đích | Có thể gộp case/dấu cần phân biệt. | Chọn strength cho sort/search riêng. |
| Không test Unicode decomposed | Hai tên trông giống nhưng khác String.equals. | Kiểm tra normalization, CANONICAL_DECOMPOSITION. |
| Thay `Locale.setDefault` trên từng request | Ảnh hưởng luồng khác. | Truyền Locale tường minh. |
| Thấy ký tự tiếng Việt in sai trong terminal rồi kết luận sort sai | Có thể do console encoding/font. | In ID/code point để tách vấn đề. |
| Cache CollationKey qua nhiều version | Dữ liệu/thuật toán collation có thể thay đổi. | Cache có version và invalidation rõ. |
| Nghĩ mọi JDK trả đúng một thứ tự tên | Dữ liệu locale provider/JDK khác nhau. | Regression test trên runtime triển khai. |
| Dùng comparator dựa vào trường thay đổi sau khi chèn TreeMap | Cây có thể không còn đúng thứ tự. | Không mutate sort key trong sorted collection. |

## 15. Ma trận kiểm thử cho danh sách người Việt

| Nhóm test | Mẫu nên có | Điều cần kiểm tra |
| --- | --- | --- |
| Chữ cái khác nhau | `An`, `Bình`, `Dung`, `Đức` | Thứ tự có lý theo quy tắc sort ứng dụng. |
| Chữ Đ và D | `Dung`, `Đung` | Sự khác biệt được Collator/runtime xử lý ra sao. |
| Nguyên âm khác dấu | `An`, `Ân`, `Ăn`, `Án` | Các mức strength và dữ liệu vi-VN. |
| Dấu thanh | `Hà`, `Há`, `Hả`, `Hã`, `Hạ` | Thứ tự khi các chữ nền giống nhau. |
| Chữ hoa/thường | `An`, `an`, `AN` | PRIMARY/TERTIARY khác nhau; chính sách tìm kiếm. |
| Unicode normalization | `á` và `a + U+0301` | Collator có decomposition và equality policy. |
| Hai người trùng tên | Hai ID khác nhưng cùng given/family | Cả hai còn trong List; có tie-break quyết định. |
| Tên gọi ghép | `Minh Anh`, `Hồng Nhung` | Không tự phân tích sai từ cuối. |
| Họ gần giống | `Đặng`, `Đỗ`, `Dương` | Sort theo họ khi yêu cầu, không dùng given comparator. |
| Dữ liệu thiếu | null/chuỗi rỗng/space | Validator hoặc null policy rõ ràng. |
| Whitespace đặc biệt | U+0020, U+00A0, U+202F | Có chính sách chuẩn hóa và dữ liệu nguồn bất biến. |
| Tên quốc tế | Tên Latin khác hoặc chữ viết khác | Support/fallback và trải nghiệm người dùng. |
| Lượng dữ liệu lớn | 10.000–100.000 bản ghi kiểm thử | Hiệu năng, tính ổn định, cân nhắc CollationKey. |
| Nhiều JDK | JDK 17, 21, 23+ theo môi trường | Snapshot/fallback/provider changes nếu cần. |

### Kiểm thử hợp đồng Comparator

Bên cạnh test thứ tự mong muốn, cần kiểm tra:

```text
compare(a, a) == 0

sign(compare(a, b)) == -sign(compare(b, a))

Nếu compare(a,b) > 0 và compare(b,c) > 0
thì compare(a,c) > 0.

Nếu compare(a,b) == 0 thì dấu compare(a,z)
phải bằng dấu compare(b,z) với mọi z.
```

Đây là **pseudocode test**, không phải cú pháp Java chạy nguyên xi. Với comparator cho đối tượng `Person`, test thêm:

- Nếu ID được kỳ vọng duy nhất trong nguồn, hai record khác ID phải có kết quả khác 0 sau tie-break.
- Một danh sách có N người đầu vào phải giữ nguyên N phần tử sau `List.sort`.
- Thứ tự không phụ thuộc thứ tự map/hash iteration khi các khóa so sánh đã được phân giải bằng ID.
- Không sửa `Collator` hoặc các field quyết định thứ tự khi phép sort đang chạy.
- Các tên lỗi/null nên được reject hoặc đặt vị trí rõ trước khi gọi Collator.

**Quan trọng:** so sánh sau sort về mặt hiển thị và so sánh theo identity nghiệp vụ là hai phép test khác nhau.

## 16. Gợi ý thiết kế cho ứng dụng thật

Một pipeline tương đối an toàn là:

```text
UI/Form/Input
    |
    v
Validation (tên có đủ các thành phần theo domain?)
    |
    v
Data model (ID, family, middle, given, displayName)
    |
    +----> Storage theo ID (không phụ thuộc collation)
    |
    +----> Search index (có chính sách dấu/case rõ)
    |
    +----> UI sorting: Collator(vi-VN) + Comparator fields + ID
                 |
                 v
            List<Person> đã sắp xếp
                 |
                 v
       Render tên theo displayName, giữ Unicode gốc
```

Những quyết định cần viết thành tài liệu:

1. UI mặc định sắp theo **given** hay **family**? Người dùng có thể chuyển chế độ không?
2. Nếu given có nhiều từ, dùng toàn bộ cụm hay một “sort key” khác do người dùng chỉ định?
3. Cùng tên, khác họ: dùng họ rồi đệm, hay dùng một thứ tự khác?
4. Hai người trùng mọi trường tên: ID nào quyết định thứ tự?
5. Tên được phép chỉnh sửa: có cần invalidate sort cache hoặc index không?
6. Có chuẩn hóa Unicode NFC ở biên dữ liệu không? Giữ raw display name như thế nào?
7. Search không dấu có dùng cùng quan hệ tương đương như sort không? Nếu khác, UI giải thích ra sao?
8. Locale/JDK thay đổi: danh sách lưu sẵn theo thứ tự nào, cache tái dựng khi nào?
9. Dữ liệu tên hiển thị trong Excel/CSV/API có cần giữ nguyên Unicode và encoding UTF-8 không?
10. Có cần so sánh theo nơi cư trú/ngôn ngữ người xem thay vì locale Việt cố định không?

Không nên ép logic sắp xếp, tìm kiếm, xác thực danh tính và lưu trữ cùng dùng một comparator chỉ vì tất cả đều “liên quan đến tên”.

## 17. Bài tập thực hành

**Bài 1 — Chạy mẫu:** biên dịch và chạy `VietnameseNameSortDemo.java` bằng JDK 17+. Dùng bảng ID để đọc `givenIds` và `familyIds`. Giải thích tại sao chúng khác nhau và ghi phiên bản JDK đang dùng.

**Bài 2 — So sánh với String.compareTo:** thêm vài tên `An`, `Án`, `Ăn`, `Ân`, `Anh` rồi sort bằng `String.compareTo` và `Collator vi-VN`. Không đoán kết quả dựa trên bảng mã Unicode; hãy in ID/code point để so.

**Bài 3 — Các mức strength:** clone Collator, lần lượt đặt PRIMARY/SECONDARY/TERTIARY/IDENTICAL; so `An`/`an`, `An`/`Án`, `Dung`/`Đung`. Ghi cặp nào cho compare==0 và lý giải nhu cầu dùng từng strength.

**Bài 4 — Tên gọi ghép:** thay một record bằng tên gọi `Minh Anh`, thêm một record có `given="Anh"`. Sắp theo given đã được lưu đầy đủ. Trả lời vì sao lấy từ cuối của fullName làm given sẽ tạo kết quả sai theo yêu cầu của dữ liệu.

**Bài 5 — Hai cách Unicode viết á:** tạo `"\u00E1"` và `"a\u0301"`. So `String.equals` và Collator có `CANONICAL_DECOMPOSITION`. Thử `Normalizer.Form.NFC` nếu sản phẩm cần dạng lưu chuẩn hóa.

**Bài 6 — Không mất người:** chèn hai Person khác ID nhưng trùng tên vào `List`, sort rồi xác nhận đủ hai ID. So sánh với TreeSet chỉ so tên; thiết kế lại bằng Map theo ID + List đã sort.

**Bài 7 — Null và whitespace:** chuẩn bị tên có null, rỗng, NBSP và dấu cách thừa. Viết validator/canonicalization với policy tường minh; đừng âm thầm biến dữ liệu khác nghĩa thành cùng tên.

**Bài 8 — Hiệu năng:** tạo 50.000 bản ghi từ dữ liệu mẫu mở rộng, benchmark comparator trực tiếp và giải pháp cache `CollationKey`. Test checksum/thứ tự như nhau, memory footprint và điều kiện cache invalidation.

**Bài 9 — Hợp đồng API:** thiết kế một endpoint trả người theo ID và các trường tên gốc, cho UI lựa chọn sort theo given/family. Không gửi chuỗi tên đã đảo, loại dấu hoặc lưu collation key như ID.

**Bài 10 — Regression đa phiên bản:** chạy cùng sample trên các JDK/vendor mà sản phẩm sẽ deploy. So sánh thứ tự và chú thích khác biệt; xác định nhóm cặp tên tối quan trọng cần giữ thứ tự dự kiến nếu ứng dụng yêu cầu luật riêng.

### Checklist cuối bài

- [ ] Tạo Collator cho `vi-VN` một cách tường minh.
- [ ] Hiểu Collator so sánh theo locale khác `String.compareTo` theo UTF-16.
- [ ] Phân biệt sắp xếp theo tên gọi và theo họ — là quyết định nghiệp vụ.
- [ ] Có data model chứa ID, family, middle, given, không giả định từ cuối luôn là tên.
- [ ] Biết chọn strength và decomposition phù hợp, có test cho tên Unicode.
- [ ] Xây được comparator theo given/family/middle/ID và sắp xếp List mà không mất record.
- [ ] Biết TreeSet/TreeMap dựa trên compare==0, có thể gộp tên khác nhau.
- [ ] Giữ Unicode gốc; không loại dấu để chữa lỗi console, không trộn encoding với collation.
- [ ] Có test null, dấu, hoa/thường, tên ghép, trùng tên và dữ liệu lớn.
- [ ] Không thay đổi Collator đang dùng trong sorted collection, không cache CollationKey xuyên version một cách mù quáng.
- [ ] Kiểm chứng trên JDK/provider triển khai nếu thứ tự từng tên cần tính tái lập cao.

## 18. Tài liệu tham khảo

- Java 17 `Collator` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Java 17 `CollationKey` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html
- Java 17 `Comparator` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html
- Java 17 `TreeSet` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html
- Java 17 `Normalizer` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html

**Kết luận:** Để **sắp xếp tên tiếng Việt bằng Collator**, cần kết hợp hai tầng: **Collator vi-VN** quyết định thứ tự giữa các chuỗi theo locale, còn **Comparator theo các trường họ/đệm/tên/ID** quyết định nghiệp vụ muốn sắp theo đâu và phân giải các bản ghi trùng. Lưu tên theo logical Unicode và identity độc lập, dùng List để hiển thị, test strength/decomposition và runtime. Đừng giao việc phân tích họ tên, xóa dấu hoặc xác định danh tính người cho Collator — API này chỉ so sánh chuỗi, không thay thế mô hình dữ liệu.
