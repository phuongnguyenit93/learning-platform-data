# Java 17: Phân biệt tính năng mới với tính năng được kế thừa

**Chủ đề:** Định hướng Java 17  
**Mục tiêu:** Nhìn vào một tính năng đang dùng được trên Java 17 và xác định đúng: tính năng đó **lần đầu xuất hiện ở bản nào**, **đã ổn định ở bản nào**, và **có nên sử dụng trong mã nguồn Java 17 hiện nay không**.

Java 17 là một phiên bản Java được phát hành theo nhịp cập nhật của nền tảng, đồng thời là một mốc hỗ trợ dài hạn (LTS). Khi một dự án chọn Java 17, dự án nhận được **toàn bộ các tính năng ổn định tích lũy từ các bản trước**, cộng với những thay đổi được đưa vào Java 17. Vì vậy, “dùng được trong Java 17” **không đồng nghĩa** với “mới xuất hiện ở Java 17”.

## 1. Ba câu hỏi phải tách biệt

Với mỗi tính năng, hãy xác định ba thông tin:

1. **Phiên bản giới thiệu:** Nó xuất hiện lần đầu trong bản Java/JDK nào? Lần đầu có thể chỉ ở trạng thái *preview*.
2. **Phiên bản ổn định:** Từ bản nào có thể sử dụng tính năng chính thức mà không bật cờ thử nghiệm?
3. **Trạng thái trên Java 17:** Là tính năng ngôn ngữ, API thư viện, thay đổi của JVM/JDK, hay một cơ chế thử nghiệm?

Ví dụ:

- `record` đã từng được giới thiệu ở dạng preview trong Java 14, nhưng **chính thức từ Java 16**. Java 17 **kế thừa** `record`.
- `sealed class` từng có dạng preview trong Java 15 và 16, nhưng **chính thức từ Java 17**. Vì vậy, đây là một điểm mới ổn định của Java 17.
- Pattern matching trong `switch` có mặt ở Java 17 nhưng **chỉ là preview trong chính Java 17**. Không được gọi nó là một tính năng ngôn ngữ ổn định của Java 17.

> **Quy tắc đọc tài liệu:** Từ “introduced”, “previewed”, “finalized” và “available” mô tả các mốc khác nhau. Hãy ưu tiên mốc **finalized/standard** khi lựa chọn cú pháp dùng lâu dài.

## 2. Bản đồ tính năng được kế thừa

Bảng sau tập trung vào các tính năng còn thực tế, hữu ích khi viết và bảo trì ứng dụng Java hiện đại. Cột “Mốc” biểu thị phiên bản mà tính năng trở thành **chính thức**, không phải thời điểm preview đầu tiên.

| Tính năng | Mốc chính thức | Vai trò khi chạy trên Java 17 |
|---|---:|---|
| Lambda expressions, Stream API | Java 8 | Nền tảng xử lý hàm, tập hợp dữ liệu; **kế thừa** |
| `Optional`, Date/Time API `java.time` | Java 8 | API chuẩn phổ biến; **kế thừa** |
| Java Platform Module System (`module-info.java`) | Java 9 | Tổ chức module và đóng gói; **kế thừa** |
| Factory methods `List.of`, `Set.of`, `Map.of` | Java 9 | Tạo collection không cho phép sửa; **kế thừa** |
| Suy luận kiểu biến cục bộ `var` | Java 10 | Giảm lặp kiểu ở nơi khai báo biến cục bộ; **kế thừa** |
| HTTP Client chuẩn `java.net.http.HttpClient` | Java 11 | Gọi HTTP đồng bộ/bất đồng bộ; **kế thừa** |
| `String.isBlank`, `strip`, `lines` | Java 11 | Tiện ích xử lý chuỗi; **kế thừa** |
| `switch` expression, `case ... ->`, `yield` | Java 14 | Viết `switch` có thể trả về giá trị; **kế thừa** |
| Text blocks `"""..."""` | Java 15 | Khai báo chuỗi nhiều dòng dễ đọc; **kế thừa** |
| `record` | Java 16 | Khai báo lớp mang dữ liệu gọn và rõ; **kế thừa** |
| Pattern matching cho `instanceof` | Java 16 | Kiểm tra kiểu và ràng buộc biến trong một bước; **kế thừa** |
| `Stream.toList()` | Java 16 | Thu kết quả stream thành danh sách không cho phép sửa; **kế thừa** |
| `sealed` class/interface | **Java 17** | Khống chế tập kiểu con được phép kế thừa; **mới ổn định ở 17** |
| `java.util.random.RandomGenerator` và các thuật toán PRNG mở rộng | **Java 17** | API/thuật toán sinh số giả ngẫu nhiên; **mới ở 17** |

### 2.1. `var` là của Java 10

`var` cho phép trình biên dịch suy ra kiểu tĩnh từ biểu thức khởi tạo:

```java
var name = "Java";             // String
var numbers = List.of(1, 2, 3); // List<Integer>
```

`var` **không** làm Java trở thành ngôn ngữ có biến kiểu động. Không thể dùng `var` làm kiểu của field, tham số phương thức hoặc kiểu trả về. Ví dụ trên cần `import java.util.List;`.

### 2.2. `switch` expression là của Java 14

```java
enum OrderStatus { NEW, PAID, CANCELLED }

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
```

Cấu trúc này là `switch` expression **đã ổn định** trong Java 14, khác với *pattern matching for switch* chỉ ở trạng thái preview tại Java 17. `switch` expression giúp mã ngắn hơn và tránh lỗi quên `break` trong cách viết `case` truyền thống.

### 2.3. Text blocks là của Java 15

```java
String json = """
        {
          "id": 17,
          "name": "Java"
        }
        """;
```

Text blocks là chuỗi Java `String` thông thường, không phải kiểu dữ liệu JSON mới. Nó hữu ích với JSON mẫu, SQL hoặc nội dung nhiều dòng; không thay thế tham số hóa truy vấn SQL và không tự động bảo vệ đầu vào.

### 2.4. `record` và pattern matching cho `instanceof` là của Java 16

```java
record User(int id, String name) {}

static String display(Object value) {
    if (value instanceof User user) {
        return user.id() + ": " + user.name();
    }
    return "Không phải User";
}
```

`record` tự tạo các thành phần tiêu chuẩn như constructor theo thành phần, accessor, `equals`, `hashCode` và `toString`. Nó hợp với đối tượng biểu diễn dữ liệu, nhưng **không bảo đảm bất biến sâu**: nếu một thành phần giữ đối tượng có thể sửa, bản thân đối tượng đó vẫn có thể thay đổi.

Cú pháp `value instanceof User user` giúp không phải ép kiểu lại sau khi kiểm tra. Cả hai tính năng đều **ổn định trước Java 17**.

## 3. Những thay đổi thực sự thuộc Java 17

Có thể chia thành **tính năng ngôn ngữ**, **API thư viện**, và **thay đổi hành vi/hạ tầng JDK**. Đừng gom tất cả vào một nhóm “cú pháp mới”.

| Nhóm | Thay đổi ở Java 17 | Ý nghĩa thực hành |
|---|---|---|
| Ngôn ngữ | **Sealed Classes** (JEP 409) được chuẩn hóa | Mô hình hóa tập kiểu con hữu hạn, hữu ích cho domain model |
| Thư viện | **Enhanced Pseudo-Random Number Generators** (JEP 356) | Dùng `RandomGenerator` và các họ thuật toán khác nhau |
| Thư viện/bảo mật | **Context-Specific Deserialization Filters** (JEP 415) | Kiểm soát lọc đối tượng được giải tuần tự hóa theo ngữ cảnh |
| Tương thích/đóng gói | **Strongly Encapsulate JDK Internals** (JEP 403) | Mã phụ thuộc API nội bộ JDK có thể phải được sửa |
| Ngữ nghĩa JVM/ngôn ngữ | **Always-Strict Floating-Point Semantics** (JEP 306) | Thống nhất ngữ nghĩa dấu phẩy động nghiêm ngặt |
| Hệ điều hành/đồ họa | Hỗ trợ macOS/AArch64 (JEP 391), pipeline Java 2D dùng Metal (JEP 382) | Tác động chủ yếu đến nền tảng triển khai |

Các thay đổi thư viện và runtime cũng là “mới ở Java 17”, dù người học không nhìn thấy một từ khóa mới nào.

### 3.1. Sealed classes: điểm mới ngôn ngữ nổi bật của Java 17

Một `sealed` class hoặc interface xác định rõ những kiểu nào được phép **kế thừa trực tiếp**:

```java
sealed interface Payment permits CardPayment, BankTransfer {}

final class CardPayment implements Payment {}

non-sealed class BankTransfer implements Payment {}
```

Trong ví dụ:

- `Payment` cho phép hai kiểu triển khai trực tiếp: `CardPayment` và `BankTransfer`.
- `final` nghĩa là `CardPayment` không thể bị kế thừa tiếp.
- `non-sealed` cho phép `BankTransfer` tiếp tục có lớp con không bị danh sách `permits` hạn chế.
- Một lớp con trực tiếp của kiểu `sealed` phải được khai báo thích hợp là `final`, `sealed` hoặc `non-sealed`. Một `record` triển khai interface `sealed` là kiểu `final` một cách ngầm định.

Những kiểu có trong `permits` còn phải tuân thủ ràng buộc vị trí của Java: trong cùng named module với kiểu `sealed`; nếu ở unnamed module thì phải cùng package. `sealed` giúp quản lý **quan hệ kế thừa tại thời điểm biên dịch**, không phải cơ chế phân quyền người dùng hay bảo mật dữ liệu.

**Khi nên dùng:** Domain có số biến thể được kiểm soát, ví dụ trạng thái kết quả xử lý, kiểu sự kiện, các nhánh của cây biểu thức. Khi muốn API cho phép bên thứ ba tự do triển khai, một interface không `sealed` thường phù hợp hơn.

### 3.2. `RandomGenerator`: API mới của Java 17

```java
import java.util.random.RandomGenerator;

public class Dice {
    public static void main(String[] args) {
        RandomGenerator random = RandomGenerator.of("L64X128MixRandom");
        int roll = random.nextInt(1, 7); // 1 đến 6
        System.out.println(roll);
    }
}
```

Đây là API mới trong package `java.util.random` của Java 17. Nó mở rộng lựa chọn thuật toán và đưa ra các interface thống nhất cho PRNG. Những API lâu đời như `java.util.Random` vẫn tồn tại và không phải mới ở Java 17.

**Lưu ý bảo mật:** PRNG phục vụ mô phỏng, kiểm thử hoặc mục đích thống kê **không mặc nhiên an toàn cho khóa, token, OTP**. Khi cần số ngẫu nhiên có tính bảo mật, dùng `java.security.SecureRandom` phù hợp; `SecureRandom` là API có từ trước, không phải tính năng mới của Java 17.

### 3.3. Đóng gói mạnh các API nội bộ JDK: tác động khi nâng cấp

Java 17 siết quyền truy cập đến nhiều package, class hoặc thành viên **nội bộ** của JDK qua JEP 403. Dự án hoặc thư viện cũ dùng reflection để chạm vào cấu trúc nội bộ có thể gặp lỗi như:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible: module java.base does not "opens ..."
```

Hướng xử lý lâu dài là cập nhật thư viện và chuyển sang **API công khai, được hỗ trợ**. Khi chẩn đoán ứng dụng cũ, lệnh `jdeps --jdk-internals` có thể giúp phát hiện phụ thuộc API nội bộ ở bytecode:

```bash
jdeps --jdk-internals app.jar
```

Tùy trường hợp, các tùy chọn JVM như `--add-opens` có thể giúp chuyển tiếp một thời gian; chúng không nên trở thành thiết kế API chính. Đây là **thay đổi hành vi khi chuyển lên Java 17**, dù code không dùng `sealed` hay `RandomGenerator`.

### 3.4. Những thay đổi khác cần biết đúng phạm vi

- **JEP 415:** Mở rộng khả năng cấu hình bộ lọc giải tuần tự hóa `ObjectInputFilter` theo từng ngữ cảnh. Giải tuần tự hóa dữ liệu không tin cậy vẫn phải có kiểm soát; có thêm bộ lọc không khiến mọi dữ liệu tự động an toàn.
- **JEP 306:** Khôi phục ngữ nghĩa phép toán dấu phẩy động luôn nghiêm ngặt. Đây là thay đổi quy tắc thực thi, không phải cú pháp mới để viết ứng dụng thông thường.
- **JEP 391 và 382:** Cải thiện tương thích với phần cứng Apple Silicon và đồ họa trên macOS. Đây là thay đổi JDK/nền tảng, không phải tính năng lập trình hướng đối tượng.
- **Security Manager:** Java 17 đã đánh dấu `SecurityManager` là *deprecated for removal* (JEP 411). Không nên chọn nó làm nền tảng bảo mật cho thiết kế mới.

## 4. Tính năng có mặt ở Java 17 nhưng chưa phải chuẩn ổn định

**Pattern matching for `switch` (JEP 406)** là *preview* trong Java 17. Khác với `switch` expression đã ổn định từ Java 14, pattern matching cho phép `case` kiểm tra kiểu hoặc mẫu dữ liệu. Trên Java 17, mã dùng cú pháp preview cần quy trình biên dịch và chạy có bật `--enable-preview`; nó **không thuộc tập cú pháp ổn định mặc định** của Java 17. Pattern matching for switch về sau mới được chuẩn hóa ở Java 21.

Java 17 còn có các API *incubator*, ví dụ Foreign Function & Memory API (JEP 412) và Vector API phiên bản thử nghiệm (JEP 414). Trạng thái incubator có nghĩa API đang được đánh giá và có thể thay đổi. Đối với dự án cần **tương thích chuẩn Java 17 lâu dài**, ưu tiên API ổn định; không lấy API incubator ở Java 17 làm khuôn mẫu sản xuất.

**Cách phân biệt nhanh:**

| Trường hợp | Kết luận đúng cho Java 17 |
|---|---|
| `record User(...)` | Được hỗ trợ ổn định, **kế thừa từ Java 16** |
| `if (x instanceof String s)` | Được hỗ trợ ổn định, **kế thừa từ Java 16** |
| `return switch (x) { ... };` | `switch` expression ổn định, **kế thừa từ Java 14** |
| `sealed interface X permits A, B` | **Chuẩn hóa trong Java 17** |
| `RandomGenerator` | **API mới được bổ sung ở Java 17** |
| `switch` có `case String s ->` | **Preview trên Java 17**, không biên dịch mặc định như cú pháp ổn định |
| Truy cập reflective vào nội bộ `java.base` | Có thể bị chặn mạnh hơn trên Java 17 do JEP 403 |

## 5. Ví dụ tổng hợp: một chương trình Java 17 dùng cả tính năng mới lẫn kế thừa

Lưu file bên dưới thành `Java17FeatureMap.java`:

```java
import java.util.random.RandomGenerator;

public class Java17FeatureMap {

    // MỚI Ở JAVA 17: sealed interface đã ổn định.
    sealed interface Result permits Success, Failure {}

    // KẾ THỪA TỪ JAVA 16: record.
    record Success(String value) implements Result {}
    record Failure(String reason) implements Result {}

    static String describe(Result result) {
        // KẾ THỪA TỪ JAVA 16: pattern matching cho instanceof.
        if (result instanceof Success success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Thất bại: " + failure.reason();
        }
        throw new IllegalStateException("Kiểu kết quả không mong đợi");
    }

    public static void main(String[] args) {
        // KẾ THỪA TỪ JAVA 10: var.
        var result = new Success("Tạo đơn hàng");

        // KẾ THỪA TỪ JAVA 15: text block.
        String payload = """
                {
                  "event": "order-created"
                }
                """;

        // MỚI Ở JAVA 17: RandomGenerator.
        RandomGenerator random = RandomGenerator.of("L64X128MixRandom");

        System.out.println(describe(result));
        System.out.println(payload);
        System.out.println("Số từ 1 đến 6: " + random.nextInt(1, 7));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc JDK mới hơn có hỗ trợ target 17:

```bash
javac --release 17 Java17FeatureMap.java
java Java17FeatureMap
```

Chương trình trên chỉ sử dụng **tính năng ổn định** trong Java 17, nên không cần `--enable-preview`. Giá trị số ngẫu nhiên có thể khác nhau ở các lần chạy.

Điều đáng chú ý: chỉ có `sealed` và `RandomGenerator` trong ví dụ thuộc nhóm **mới ở Java 17**. `record`, pattern matching cho `instanceof`, `var` và text blocks vẫn là cách viết Java 17 hợp lệ và nên tiếp tục được sử dụng đúng tình huống, dù chúng đến từ các phiên bản trước.

## 6. Phân biệt “chạy bằng Java 17” và “biên dịch cho Java 17”

Ba khái niệm sau liên quan nhưng khác nhau:

- **JDK đang dùng:** Bộ công cụ thực hiện `javac`, `java` và các tiện ích phát triển.
- **Mức ngôn ngữ/API đích:** Chọn bằng `javac --release N`; quy định những tính năng ngôn ngữ và API nền tảng có thể sử dụng khi biên dịch.
- **Phiên bản runtime triển khai:** JVM thực sự chạy ứng dụng; phải hiểu được class file và các API mà ứng dụng yêu cầu.

Ví dụ, sử dụng một JDK đủ mới để chạy:

```bash
javac --release 17 Java17FeatureMap.java
```

đồng nghĩa biên dịch theo mức Java 17 (class-file major version **61**). Class file này **không chạy trên Java 11**. Ngược lại, một ứng dụng Java 11 thông thường có thể chạy trên JDK 17 nếu không vướng thay đổi hành vi, API hoặc thư viện phụ thuộc; vẫn cần kiểm thử tương thích thực tế.

Nếu sản phẩm bắt buộc chạy trên Java 11, việc dùng JDK 17 để phát triển **không cho phép** sử dụng `sealed` hay `RandomGenerator` rồi hy vọng ứng dụng vẫn chạy trên Java 11. Cần đặt mức `--release 11` và lựa chọn API tương ứng.

### Checklist khi đọc mã nguồn hoặc nâng cấp dự án

1. Nhìn vào `build.gradle`, `pom.xml` hoặc cấu hình biên dịch để biết source/target/release mà dự án cam kết.
2. Với tính năng ngôn ngữ, kiểm tra **phiên bản được chuẩn hóa**, không lấy phiên bản preview làm mốc.
3. Với API, kiểm tra package/class/method có tồn tại trong phiên bản Java đích hay không.
4. Với ứng dụng cũ, rà phụ thuộc thư viện và các API nội bộ JDK khi chuyển runtime lên Java 17.
5. Không dùng ví dụ đòi hỏi preview/incubator làm mã sản xuất tiêu chuẩn của Java 17.

## 7. Một số hiểu nhầm thường gặp

**“Java 17 có `record`, vậy `record` là tính năng mới của Java 17.”**  
Sai. `record` ổn định từ Java 16; Java 17 chỉ kế thừa.

**“`switch` với cú pháp mũi tên và pattern matching trong `switch` là cùng một tính năng.”**  
Sai. `case VALUE ->` trong `switch` expression đã ổn định từ Java 14; pattern matching `case Type variable ->` chỉ là preview trên Java 17.

**“Sealed class giống final class.”**  
Không hoàn toàn. `final` ngăn mọi kế thừa; `sealed` cho phép đúng một danh sách kiểu con trực tiếp được chỉ định.

**“Java 17 là LTS nên tất cả tính năng xuất hiện trong Java 17 đều ổn định.”**  
Sai. LTS là đặc tính của chu kỳ hỗ trợ phát hành; trong Java 17 vẫn có các JEP preview/incubator.

**“Đổi runtime sang Java 17 là tự động dùng được cú pháp Java 17 trong mọi dự án.”**  
Sai. Cấu hình biên dịch có thể vẫn đặt `--release 8` hoặc `--release 11`, và các công cụ build/IDE cũng phải hỗ trợ mức ngôn ngữ cần dùng.

**“Java 17 có `RandomGenerator`, vậy có thể dùng mọi PRNG để tạo token bảo mật.”**  
Sai. Dùng `SecureRandom` cho nhu cầu mật mã, không dùng các PRNG thông thường để thay thế.

## 8. Câu hỏi tự luyện

**Tình huống 1:** Nhóm phát triển viết DTO bằng `record` khi nâng từ Java 11 lên Java 17. Họ nên nói “đã áp dụng một tính năng mới của Java 17” hay “đã áp dụng tính năng được Java 17 kế thừa”?

**Đáp án:** `record` là tính năng ổn định từ **Java 16**, nên là tính năng **được Java 17 kế thừa**. Việc nâng từ Java 11 lên 17 mới giúp dự án có thể dùng nó không khiến mốc phát hành của `record` thay đổi.

**Tình huống 2:** Một thư viện Java 11 dùng reflection truy cập chi tiết triển khai bên trong `java.base` và lỗi sau khi nâng runtime lên 17. Đây là vấn đề ở cú pháp mới hay thay đổi cơ chế của JDK?

**Đáp án:** Đây có thể là tác động của **đóng gói mạnh các API nội bộ ở Java 17**. Cần kiểm tra stack trace, nâng phiên bản thư viện và chuyển sang API được hỗ trợ.

**Tình huống 3:** Muốn biểu diễn kết quả nghiệp vụ chỉ có `Success`, `Failure` và `Pending`, không cho bên ngoài bổ sung kiểu thứ tư. Nên cân nhắc điều gì?

**Đáp án:** Có thể dùng một `sealed interface` với danh sách `permits` cho các kiểu kết quả; mỗi kiểu con trực tiếp phải đáp ứng quy tắc `final`, `sealed` hoặc `non-sealed`. Nếu mục tiêu thực sự là giới hạn toàn bộ cây kiểu, tránh mở nhánh `non-sealed` ngoài ý muốn.

**Tình huống 4:** Một ví dụ trên mạng dùng `case String s ->` bên trong `switch` và tác giả gọi đó là “Java 17 chuẩn”. Nhận định có chính xác không?

**Đáp án:** Không. Pattern matching for `switch` là **preview trên Java 17**, dù `switch` expression nói chung đã ổn định từ Java 14.

## 9. Tài liệu chính thức để tra cứu

- [Oracle Java SE 17 — Java Language Changes](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): bảng mốc chuẩn hóa các cú pháp ngôn ngữ qua từng phiên bản.
- [Oracle JDK 17 — Significant Changes](https://docs.oracle.com/en/java/javase/17/migrate/significant-changes-jdk-release.html): thay đổi API, runtime và lưu ý di chuyển lên Java 17.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): đặc tả và động cơ thiết kế `sealed`.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395) và [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): hai tính năng được chuẩn hóa từ Java 16.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): API PRNG của Java 17.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): thay đổi quan trọng về tương thích.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): xác nhận trạng thái preview của tính năng này trong Java 17.

**Điểm cần ghi nhớ:** Xác định phiên bản theo **mốc chuẩn hóa**. Trên Java 17, có thể dùng nhiều cú pháp hiện đại xuất hiện từ Java 8–16; những điểm mới nổi bật của chính Java 17 gồm `sealed` đã ổn định, API `RandomGenerator` và các cải tiến về đóng gói, bảo mật, runtime và nền tảng.
