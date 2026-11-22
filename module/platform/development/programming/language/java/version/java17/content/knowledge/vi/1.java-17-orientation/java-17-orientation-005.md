# Phân biệt tính năng chính thức, preview và incubator trong Java 17

Khi đọc danh sách tính năng của Java 17, bạn sẽ gặp các nhãn như **final/permanent**, **preview** và **incubator**. Các nhãn này thể hiện **mức độ hoàn thiện và cam kết tương thích của từng tính năng tại một phiên bản JDK cụ thể**. Biết phân biệt chúng giúp bạn chọn API và cú pháp phù hợp, cấu hình biên dịch đúng, đồng thời đánh giá rủi ro khi nâng cấp Java.

> **Phạm vi:** Bài học dùng **JDK 17** để thực hành và đối chiếu với một số phiên bản Java mới hơn khi cần. Tình trạng của tính năng luôn phải gắn với **phiên bản Java**: một tính năng là preview ở Java 17 có thể đã trở thành chính thức ở Java 21. Ví dụ incubator của Java 17 dùng để hiểu cơ chế, không phải hướng dẫn áp dụng API thử nghiệm cũ cho dự án Java mới.

## 1. Ba mức độ trưởng thành của tính năng

| Tiêu chí | Chính thức (final/permanent) | Preview | Incubator |
|---|---|---|---|
| Mục tiêu | Cung cấp tính năng đã hoàn thiện để dùng thông thường | Đưa thiết kế tương đối hoàn chỉnh ra cộng đồng thử nghiệm, thu thập phản hồi | Thử nghiệm API hoặc mô-đun mới trước khi quyết định hình dạng lâu dài |
| Phạm vi thường gặp | Cú pháp ngôn ngữ, JVM, API chuẩn | Tính năng ngôn ngữ/JVM; có thể có API ở trạng thái preview | Thư viện/API hoặc mô-đun thử nghiệm được phân phối trong JDK |
| Tình trạng trong JDK 17 | Dùng trực tiếp theo điều kiện thông thường | Mặc định tắt; phải bật rõ ràng khi biên dịch và chạy | Thường nằm trong mô-đun `jdk.incubator.*`; cần khai báo mô-đun khi dùng |
| Tùy chọn điển hình | Không cần `--enable-preview` | `--enable-preview` | `--add-modules <tên-mô-đun>` cho chương trình không khai báo mô-đun |
| Khả năng thay đổi ở bản Java sau | Có mức cam kết tương thích cao hơn; vẫn có thể được cải tiến hoặc bị loại bỏ theo quy trình | Có thể đổi cú pháp/hành vi, tiếp tục preview, được chuẩn hóa hoặc bị rút lại | API/mô-đun có thể thay đổi, trở thành API chính thức ở vị trí khác hoặc bị rút khỏi JDK |
| Gợi ý sử dụng | Lựa chọn mặc định cho mã ứng dụng lâu dài | Học tập, thử nghiệm, kiểm chứng với đúng phiên bản JDK | Thử nghiệm có kiểm soát; cô lập phần phụ thuộc để dễ nâng cấp |

**Quan trọng:** “Có sẵn trong JDK” không đồng nghĩa với “đã chính thức”. Ngược lại, **LTS** (Long-Term Support) mô tả chính sách hỗ trợ của một bản phát hành Java, không biến các tính năng preview/incubator trong bản đó thành tính năng ổn định.

Trong tài liệu Java, `final` hoặc `permanent` nói về **trạng thái hoàn thiện của tính năng**. Đừng nhầm với từ khóa Java `final` dùng cho biến, phương thức hoặc lớp.

## 2. Tính năng chính thức: dùng mà không bật chế độ thử nghiệm

Tính năng chính thức đã hoàn tất quá trình chuẩn hóa áp dụng cho phiên bản Java tương ứng. Khi dùng JDK 17, những ví dụ tiêu biểu gồm:

- **Sealed classes/interfaces** — chính thức ở **Java 17**, theo [JEP 409](https://openjdk.org/jeps/409).
- **Records** — chính thức từ **Java 16**, theo [JEP 395](https://openjdk.org/jeps/395).
- **Pattern matching for `instanceof`** — chính thức từ **Java 16**, theo [JEP 394](https://openjdk.org/jeps/394).
- **Text blocks** — chính thức từ **Java 15**, theo [JEP 378](https://openjdk.org/jeps/378).
- **Switch expressions** — chính thức từ **Java 14**, theo [JEP 361](https://openjdk.org/jeps/361).

Những tính năng đã chính thức ở bản Java trước vẫn có thể được dùng bình thường trong Java 17. Việc một tính năng xuất hiện trong bài giới thiệu Java 17 không nhất thiết có nghĩa nó mới được chính thức hóa đúng ở Java 17.

### Ví dụ: `sealed`, `record` và `instanceof` trong Java 17

Tạo file `StableDemo.java`:

~~~java
sealed interface Payment permits Card, Cash {}

record Card(String lastFourDigits) implements Payment {}

record Cash(long amount) implements Payment {}

public class StableDemo {
    static String describe(Payment payment) {
        if (payment instanceof Card card) {
            return "Thanh toán bằng thẻ ****" + card.lastFourDigits();
        }
        return "Thanh toán tiền mặt";
    }

    public static void main(String[] args) {
        Payment payment = new Card("1234");
        System.out.println(describe(payment));
    }
}
~~~

Ở đây:

1. `sealed interface Payment` quy định chỉ những kiểu được cho phép mới trực tiếp triển khai giao diện này.
2. Hai `record` biểu diễn dữ liệu gọn, đồng thời đáp ứng yêu cầu về kiểu con của `sealed` vì record là kiểu cuối cùng (`final`) theo thiết kế.
3. `payment instanceof Card card` vừa kiểm tra kiểu vừa tạo biến `card` để sử dụng trong nhánh đúng.

Biên dịch và chạy bằng **JDK 17**:

~~~bash
javac --release 17 StableDemo.java
java StableDemo
~~~

Kết quả:

~~~text
Thanh toán bằng thẻ ****1234
~~~

**Không cần `--enable-preview`**. Nếu công cụ biên dịch báo không nhận ra `sealed` hay `record`, hãy kiểm tra phiên bản JDK và cấu hình `--source`/`--release` của dự án.

### Cần hiểu đúng về sự ổn định

“Tính năng chính thức” là lựa chọn phù hợp cho mã lâu dài, nhưng không có nghĩa mọi chi tiết trong thư viện sẽ bất biến mãi mãi. Java vẫn có cơ chế bổ sung API, đánh dấu `@Deprecated` và phát triển nền tảng có kiểm soát. Đặc biệt, API nội bộ `sun.*` hay `jdk.internal.*` không tự nhiên trở thành API được hỗ trợ chỉ vì nó tồn tại trong một JDK chính thức.

## 3. Preview: tính năng hoàn chỉnh để dùng thử, chưa có cam kết cuối cùng

**Preview feature** là tính năng đã có thiết kế, đặc tả và triển khai đủ để cộng đồng dùng thử, nhưng chưa được chốt để trở thành một phần vĩnh viễn của nền tảng. Nhóm phát triển Java có thể điều chỉnh cú pháp và ngữ nghĩa dựa trên phản hồi. Đây là cơ chế được mô tả trong [JEP 12](https://openjdk.org/jeps/12).

Trong **Java 17**, ví dụ quan trọng là **Pattern Matching for `switch` (Preview)**, theo [JEP 406](https://openjdk.org/jeps/406).

### Đừng nhầm `switch expression` với pattern matching cho `switch`

Hai cách dùng `switch` khác nhau về trạng thái ở Java 17:

~~~java
// Switch expression: chính thức từ Java 14, chạy bình thường ở Java 17.
String label = switch (day) {
    case 6, 7 -> "Cuối tuần";
    default -> "Ngày thường";
};
~~~

~~~java
// Pattern matching trong switch: PREVIEW ở Java 17.
// Phải bật --enable-preview khi biên dịch và chạy.
String label = switch (value) {
    case Integer n -> "Số nguyên: " + n;
    case String s -> "Chuỗi: " + s;
    default -> "Loại khác";
};
~~~

Điểm làm cho ví dụ thứ hai là preview trong Java 17 chính là các **type pattern** như `case Integer n`, `case String s`; không phải chỉ vì nó dùng dấu mũi tên `->`.

### Ví dụ chạy được trên JDK 17

Tạo file `PreviewDemo.java`:

~~~java
public class PreviewDemo {
    static String describe(Object value) {
        return switch (value) {
            case Integer number -> "Integer: " + number;
            case String text -> "String: " + text;
            case null -> "null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(17));
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
~~~

Biên dịch:

~~~bash
javac --enable-preview --release 17 PreviewDemo.java
~~~

Chạy:

~~~bash
java --enable-preview PreviewDemo
~~~

Đầu ra:

~~~text
Integer: 17
String: Java
null
~~~

Khi biên dịch, `javac` có thể hiển thị thông báo sử dụng preview feature; đây là thông báo dự kiến.

**Vì sao phải bật ở cả hai bước?**

- `javac` cần `--enable-preview` để chấp nhận cú pháp/ngữ nghĩa preview. Với `javac` của JDK 17, sử dụng kèm `--release 17` (hoặc `--source 17`).
- `java` cần `--enable-preview` để chạy mã phụ thuộc preview của đúng phiên bản Java tương ứng. Chỉ bật ở lúc biên dịch là chưa đủ.
- Không thể dùng `javac` của JDK mới hơn để “bật lại preview của Java 17” chỉ bằng `--release 17`. Preview của mỗi bản phát hành gắn với chính bản đó. Muốn chạy ví dụ preview Java 17, hãy dùng **toolchain JDK 17**.

Về kỹ thuật, các `.class` phụ thuộc preview trong Java 17 mang phiên bản class file **61.65535**; phần minor `65535` đánh dấu phụ thuộc preview. Loại class file này bị ràng buộc với bản Java mà nó được biên dịch, khác với class file Java 17 thông thường **61.0**. Đây là một lý do khiến bản nâng cấp JDK cần biên dịch lại nguồn dùng preview.

### Điều gì xảy ra sau Java 17?

Pattern Matching for `switch` được tiếp tục thử nghiệm trong các bản Java 18–20, rồi **chính thức ở Java 21 (JEP 441)**. Điều này minh họa cách một tính năng tiến từ preview đến final. Cú pháp và các quy tắc của bản chính thức có thể khác bản preview ban đầu; khi nâng cấp dự án, hãy đọc tài liệu của **phiên bản đích**, thay vì bê nguyên mã preview Java 17 sang.

## 4. Incubator: thử nghiệm API và mô-đun trong JDK

**Incubator** thường dùng cho API hoặc mô-đun mà nhóm phát triển muốn đưa đến người dùng sớm để đo lường tính hữu ích và thu thập phản hồi về thiết kế. Chúng không phải là một phần API Java SE ổn định.

Trong **JDK 17**, hai ví dụ là:

| Tính năng ở JDK 17 | JEP | Mô-đun | Lưu ý |
|---|---|---|---|
| Vector API (Second Incubator) | [JEP 414](https://openjdk.org/jeps/414) | `jdk.incubator.vector` | Thử nghiệm cách biểu diễn các phép toán SIMD trong Java |
| Foreign Function & Memory API (Incubator) | [JEP 412](https://openjdk.org/jeps/412) | `jdk.incubator.foreign` | API thử nghiệm **của JDK 17**; không nên học cú pháp này như API hiện hành để viết ứng dụng mới |

Từ góc nhìn tương thích hiện nay, lịch sử của Foreign Function & Memory API đặc biệt hữu ích: sau nhiều giai đoạn thử nghiệm, API đã **chính thức ở Java 22** theo [JEP 454](https://openjdk.org/jeps/454), nằm trong package `java.lang.foreign`. Cần học tài liệu API chính thức của phiên bản đang sử dụng thay vì sao chép mã `jdk.incubator.foreign` cũ.

### Ví dụ: Vector API trong đúng môi trường JDK 17

Tạo file `VectorDemo.java`:

~~~java
import java.util.Arrays;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorDemo {
    public static void main(String[] args) {
        VectorSpecies<Integer> species = IntVector.SPECIES_PREFERRED;
        int lanes = species.length();

        int[] left = new int[lanes];
        int[] right = new int[lanes];

        for (int i = 0; i < lanes; i++) {
            left[i] = i;
            right[i] = 10;
        }

        IntVector a = IntVector.fromArray(species, left, 0);
        IntVector b = IntVector.fromArray(species, right, 0);

        int[] result = new int[lanes];
        a.add(b).intoArray(result, 0);

        System.out.println(Arrays.toString(result));
    }
}
~~~

Thực hiện bằng **JDK 17**:

~~~bash
javac --add-modules jdk.incubator.vector VectorDemo.java
java --add-modules jdk.incubator.vector VectorDemo
~~~

Kết quả là một mảng các số `10, 11, 12, ...`, với số phần tử tương ứng `species.length()`. Kích thước vector được chọn theo nền tảng, vì vậy không nên giả định luôn có 4 hoặc 8 phần tử. Bạn có thể thấy cảnh báo tương tự `using incubating module(s): jdk.incubator.vector` khi biên dịch/chạy; đó là cảnh báo nhắc rằng API đang trong giai đoạn incubator.

**Tại sao chỉ dùng `--add-modules` mà không dùng `--enable-preview`?**

- `--add-modules jdk.incubator.vector` yêu cầu hệ thống mô-đun phân giải thêm mô-đun incubator để mã có thể tham chiếu API của nó.
- `--enable-preview` bật preview features của ngôn ngữ/JVM/API preview được quy định cho bản JDK; nó **không thay thế** việc khai báo mô-đun incubator.
- Nếu dự án sử dụng **named modules**, thông thường cần khai báo phụ thuộc phù hợp trong `module-info.java`, chẳng hạn `requires jdk.incubator.vector;`. Cấu hình chính xác phụ thuộc cách bạn biên dịch, đóng gói và chạy ứng dụng.

Đối với hệ thống dùng lâu dài, hãy đánh giá mức phụ thuộc và khả năng thay thế bằng API ổn định. Không nên giả định tên mô-đun, package và chữ ký phương thức của bản incubator ở JDK 17 còn giữ nguyên ở các bản Java sau.

## 5. So sánh cùng một mục tiêu: chọn phương án nào?

Giả sử cần xác định loại của một đối tượng để hiển thị thông tin.

**Phương án dùng tính năng chính thức của Java 17:** dùng pattern matching cho `instanceof`.

~~~java
static String describe(Object value) {
    if (value instanceof Integer n) {
        return "Integer: " + n;
    }
    if (value instanceof String s) {
        return "String: " + s;
    }
    return value == null ? "null" : "Other";
}
~~~

Mã trên không yêu cầu bật preview và phù hợp làm lựa chọn mặc định nếu ứng dụng phải giữ mức tương thích **Java 17**.

**Phương án dùng preview trong Java 17:** dùng pattern matching cho `switch` như phần 3. Mã súc tích, nhưng kéo theo cờ biên dịch/chạy và yêu cầu điều chỉnh khi đổi JDK. Nếu dự án được phép nâng lên Java 21 hoặc mới hơn, hãy tham khảo cú pháp `switch` pattern matching **đã chính thức** của phiên bản đích.

Với **incubator**, quyết định mang tính khác biệt hơn: bạn đang chọn phụ thuộc vào một **API thử nghiệm**. Hãy dùng incubator để nghiên cứu khả năng mới hoặc thử nghiệm có kiểm soát, đồng thời chuẩn bị phương án thay thế khi cập nhật JDK.

| Bối cảnh dự án | Hướng xử lý |
|---|---|
| Dự án Java 17 phục vụ người dùng, yêu cầu triển khai và cập nhật ổn định | Ưu tiên cú pháp và API chính thức trên Java 17 |
| Muốn đánh giá một đề xuất ngôn ngữ mới | Thử preview trong nhánh/thành phần riêng, ghim JDK và bật cờ ở mọi bước |
| Muốn đánh giá thư viện thử nghiệm được phân phối trong JDK | Dùng incubator theo tài liệu của **đúng bản JDK**, cô lập phụ thuộc |
| Chuẩn bị nâng cấp Java 17 lên phiên bản mới | Kiểm tra lại trạng thái **từng tính năng** ở phiên bản đích; bỏ cờ khi tính năng đã final và sửa các thay đổi cú pháp/API nếu có |

## 6. Cách nhận biết trạng thái của một tính năng

Khi gặp cú pháp hoặc API chưa quen, làm theo thứ tự:

1. **Xác định JDK thực tế** bằng `java -version` và `javac -version`. Hai lệnh nên trỏ đến cùng phiên bản dự kiến.
2. **Tra tài liệu theo phiên bản**, ví dụ [Java 17 Language Changes Summary](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-summary.html) và release notes. Đừng suy luận từ bài hướng dẫn cho JDK khác.
3. **Xem JEP tương ứng**. Tên JEP hoặc lịch sử phát hành thường ghi rõ `Preview`, `Second Preview`, `Incubator`, `Final`.
4. **Tra Java API Documentation đúng phiên bản**. Các package `jdk.incubator.*` có ghi chú trạng thái incubator; API thử nghiệm không được xem là API tiêu chuẩn bền vững.
5. **Kiểm tra tác động lên toàn bộ vòng đời ứng dụng**: biên dịch, chạy, test, CI/CD, IDE, đóng gói và nâng cấp JDK.

Để xem các mô-đun mà bản JDK đang cài cung cấp:

~~~bash
java --list-modules
~~~

Nếu thấy `jdk.incubator.vector` trong danh sách thì bản JDK đó **có cung cấp mô-đun**. Nó không có nghĩa mô-đun đã chính thức, và cũng không bảo đảm API của phiên bản khác tương thích.

### Các lỗi/cảnh báo dễ gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac` báo preview feature disabled | Dùng cú pháp preview mà chưa bật khi biên dịch | Dùng `javac` của JDK 17 cùng `--enable-preview --release 17` |
| `java` không chạy được class phụ thuộc preview | Thiếu cờ lúc chạy hoặc chạy sai bản Java | Chạy bằng đúng JDK 17 với `java --enable-preview` |
| `package jdk.incubator.vector is not visible` hoặc không tìm thấy mô-đun | Mô-đun incubator chưa được phân giải, hoặc JDK hiện tại không chứa mô-đun đó | Kiểm tra `java --list-modules`; cấu hình `--add-modules` và toolchain phù hợp |
| Biên dịch được mã Java 17 nhưng lỗi khi dùng ví dụ trên JDK mới | Trạng thái/cú pháp preview hoặc API incubator đã thay đổi | Mở tài liệu của bản JDK mới, chuyển sang API/cú pháp đã chính thức nếu có |

**Lưu ý về công cụ build:** Nếu dự án dùng Maven hoặc Gradle, các tùy chọn cần được cấu hình cho những tác vụ thực sự có liên quan: compile, test và runtime. Chỉ thêm cờ cho một bước không có nghĩa các bước còn lại đã nhận cùng cấu hình.

## 7. Một tính năng có thể đổi trạng thái như thế nào?

Quá trình thường được hình dung như sau:

~~~text
Đề xuất / nghiên cứu
       |
       +--> Preview (có thể lặp qua nhiều bản)
       |          |
       |          +--> Final
       |          +--> Tiếp tục preview / chỉnh sửa
       |          +--> Rút lại
       |
       +--> Incubator (có thể lặp qua nhiều bản)
                  |
                  +--> API chính thức (có thể đổi package/cách dùng)
                  +--> Tiếp tục incubator / chỉnh sửa
                  +--> Rút lại
~~~

Đây là sơ đồ khái quát, không phải lộ trình bắt buộc cho mọi JEP. Ví dụ về thay đổi đã diễn ra:

- **Sealed classes:** preview ở Java 15–16, **final ở Java 17**.
- **Pattern matching for `switch`:** preview bắt đầu ở Java 17, **final ở Java 21**.
- **Foreign Function & Memory API:** từng đi qua giai đoạn incubator và preview, sau đó **final ở Java 22** với API `java.lang.foreign`.

Chính vì có thể thay đổi trạng thái, câu hỏi đúng luôn là **“Tính năng X ở Java phiên bản Y thuộc loại nào?”** thay vì chỉ hỏi “Tính năng X có phải preview không?”.

## 8. Bài tập tự kiểm tra

**Bài 1.** Với dự án sử dụng JDK 17, phân loại: `record`, `sealed interface`, `case Integer n ->` trong `switch`, và `jdk.incubator.vector.IntVector`.

**Bài 2.** Một dự án Java 17 dùng `case String s ->` trong `switch`. Nhà phát triển đã thêm `--enable-preview` lúc biên dịch nhưng quên ở lệnh `java`. Hãy giải thích vì sao chạy vẫn có thể thất bại và đưa ra lệnh đúng.

**Bài 3.** Một bài viết cũ giới thiệu `jdk.incubator.foreign` như cách mới nhất để gọi hàm native. Bạn đang phát triển trên JDK 22 hoặc mới hơn. Nên kiểm tra API nào, và tại sao?

**Gợi ý đáp án:**

1. `record` và `sealed interface` đều chính thức trong Java 17; type pattern của `switch` là preview; `IntVector` thuộc mô-đun incubator.
2. Preview phải được bật ở cả biên dịch và runtime: `javac --enable-preview --release 17 ...`, sau đó `java --enable-preview ...`, dùng đúng JDK 17.
3. Tìm tài liệu **Foreign Function & Memory API `java.lang.foreign`** đã final từ Java 22; API incubator của JDK 17 là hình thức cũ và không thích hợp để sao chép vào mã mới.

## 9. Tài liệu tham khảo

- [Oracle — Java SE 17: Language Changes Summary](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-summary.html)
- [Oracle — Java SE 17: Preview Features](https://docs.oracle.com/en/java/javase/17/language/preview-language-and-vm-features.html)
- [Oracle — Java SE 17: `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle — Java SE 17: `IntVector` API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html)
- [Oracle — Java SE 21: Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle — Java SE 22: Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [OpenJDK — JEP 12: Preview Features](https://openjdk.org/jeps/12)
- [OpenJDK — JEP 406: Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406)
- [OpenJDK — JEP 409: Sealed Classes](https://openjdk.org/jeps/409)
- [OpenJDK — JEP 414: Vector API (Second Incubator)](https://openjdk.org/jeps/414)
- [OpenJDK — JEP 441: Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [OpenJDK — JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)

