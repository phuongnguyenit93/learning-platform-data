# Phần thực hành dùng đặc tả preview Java 27 hiện hành

Bài thực hành này nằm trong module **JAVA_VERSION_JAVA26**, nhưng đề bài yêu cầu sử dụng đặc tả preview hiện hành của Java 27 để luyện cách kiểm tra một tính năng ngôn ngữ chưa ổn định. Cần phân biệt rõ hai mốc: Java 26 có lần preview thứ tư theo **JEP 530**; Java 27 có lần preview thứ năm theo **JEP 532**. Tài liệu Java 27 cho biết lần preview thứ năm không có thay đổi mang tính chuẩn tắc đáng kể so với lần thứ tư.

Có một cập nhật vòng đời rất quan trọng ở thời điểm hiện tại: ngày 11-11-2026, nhóm Java thông báo dừng phát triển tính năng Primitive Types in Patterns, `instanceof`, and `switch`. Draft JEP cho lần preview thứ sáu sẽ bị rút và tính năng sẽ bị loại khỏi JDK 28. Vì vậy, JDK 27 là môi trường hiện hành để tái hiện và học đặc tả preview này; bài thực hành có giá trị để hiểu cách dùng, kiểm tra tính an toàn và đánh giá preview, nhưng không nên dùng tính năng này làm nền tảng cho mã sản phẩm mới hoặc kỳ vọng mã sẽ tiếp tục biên dịch ở JDK 28.

## 1. Xác định đúng release và trạng thái tính năng

| Release | Đặc tả | Trạng thái |
|---|---|---|
| Java 23 | JEP 455 | Preview lần đầu |
| Java 24 | JEP 488 | Preview lần thứ hai |
| Java 25 | JEP 507 | Preview lần thứ ba |
| Java 26 | JEP 530 | Preview lần thứ tư; có điều chỉnh về unconditional exactness và dominance |
| Java 27 | JEP 532 | Preview lần thứ năm; tài liệu JLS ghi không có thay đổi chuẩn tắc so với lần preview thứ tư |
| Java 28 | Draft JEP 8393282 cho preview thứ sáu được thông báo sẽ rút | Tính năng được thông báo sẽ bị loại khỏi JDK 28 |

JDK 27 được phát hành ngày 15-09-2026. Trong tài liệu Java SE 27, Primitive Types in Patterns, `instanceof`, and `switch` vẫn được đánh dấu là **preview language feature**. Điều này có nghĩa cú pháp và ngữ nghĩa đang có trong release 27 có thể được thử nghiệm, nhưng chưa trở thành một phần ngôn ngữ ổn định.

Đừng nhầm lần preview thứ năm của JDK 27 với lần preview thứ tư của JDK 26. Khi thực hành, luôn đọc JEP và Java Language Specification của đúng release đang chạy. Đặc biệt, không dùng cú pháp Java 27 rồi biên dịch hoặc chạy bằng JDK 26 chỉ vì dự án đang nằm trong thư mục module Java 26.

## 2. Tính năng primitive patterns mở rộng điều gì?

Trước tính năng này, pattern matching chủ yếu kiểm tra kiểu tham chiếu. Primitive patterns mở rộng pattern matching để có thể sử dụng kiểu nguyên thủy trong các ngữ cảnh pattern, đồng thời mở rộng `instanceof` và `switch` cho các kiểu nguyên thủy.

Các phần chính gồm:

- **Type patterns với primitive types:** pattern có thể khai báo biến kiểu `int`, `long`, `float`, `double`, `byte`, `short`, `char` hoặc `boolean`.
- **Primitive types trong record patterns:** pattern thành phần của record có thể kiểm tra và chuyển đổi sang kiểu nguyên thủy khi phép chuyển đổi là chính xác.
- **Primitive values trong switch:** selector của switch có thể là các kiểu nguyên thủy, bao gồm `long`, `float`, `double` và `boolean`, cùng các kiểu wrapper tương ứng.
- **Safe casting với instanceof và switch:** có thể kiểm tra tại runtime liệu chuyển đổi giữa hai kiểu có giữ nguyên giá trị hay không.
- **When clauses:** có thể ràng buộc giá trị được bắt bởi primitive type pattern ở cấp cao nhất bằng biểu thức điều kiện `when`.

Điểm cốt lõi không phải là cho phép ép kiểu tùy ý. Pattern chỉ khớp khi phép chuyển đổi kiểm tra (testing conversion) thành công và không làm mất thông tin. Nhờ đó, chương trình có thể kiểm tra trước một phép chuyển đổi số thay vì ép kiểu rồi âm thầm nhận giá trị đã bị cắt cụt hoặc làm tròn.

## 3. Thực hành type pattern và instanceof với kiểu nguyên thủy

Ví dụ đơn giản nhất là kiểm tra một giá trị `float` có thể được chuyển đổi chính xác sang kiểu nào:

    public class PrimitiveTypePatterns {
        public static void main(String[] args) {
            float value = 1000.01f;

            if (value instanceof float f) {
                System.out.println("float: " + f);
            }

            if (value instanceof double d) {
                System.out.println("double: " + d);
            }

            if (value instanceof int i) {
                System.out.println("int: " + i);
            }
        }
    }

Với giá trị trên, pattern `float` khớp vì không cần chuyển đổi. Pattern `double` cũng khớp vì mọi giá trị `float` đều có thể biểu diễn chính xác dưới dạng `double`. Pattern `int` không khớp vì chuyển đổi từ `1000.01f` sang `int` sẽ làm mất phần thập phân.

Kết quả minh họa:

    float: 1000.01
    double: 1000.010009765625

Giá trị `double` trông khác chuỗi thập phân ban đầu vì `float` đã lưu một giá trị nhị phân gần nhất trước khi được mở rộng sang `double`. Phép mở rộng giữ nguyên chính xác giá trị nhị phân đang có của `float`; nó không khôi phục số thập phân lý tưởng ban đầu.

Có thể dùng pattern để kiểm tra một đối tượng wrapper trước khi lấy giá trị nguyên thủy:

    static void inspect(Object value) {
        if (value instanceof int number) {
            System.out.println("Có thể lấy int chính xác: " + number);
        } else {
            System.out.println("Không chuyển đổi chính xác sang int");
        }
    }

    // Ví dụ gọi:
    inspect(Integer.valueOf(42));
    inspect(Long.valueOf(42));
    inspect(null);

Giá trị `Integer` có thể được unbox thành `int`. Đối tượng `Long` không được tự động thu hẹp thành `int` trong testing conversion này. Giá trị `null` không khớp primitive pattern.

## 4. Kiểm tra phép chuyển đổi số có an toàn hay không

Một phép ép kiểu số thông thường có thể làm mất dữ liệu mà không ném `ClassCastException`. Ví dụ:

    int original = 2345323;
    byte converted = (byte) original;
    System.out.println(converted);

Kết quả của phép ép kiểu có thể khác xa giá trị ban đầu. Primitive `instanceof` cho phép kiểm tra xem chuyển đổi có chính xác hay không trước khi sử dụng kết quả:

    static void printByteIfSafe(int value) {
        if (value instanceof byte small) {
            System.out.println("Giá trị byte hợp lệ: " + small);
        } else {
            System.out.println("Không thể chuyển sang byte mà vẫn giữ nguyên giá trị");
        }
    }

    // 127 có thể biểu diễn chính xác bằng byte.
    printByteIfSafe(127);

    // 128 vượt miền byte có dấu.
    printByteIfSafe(128);

Với `127`, pattern khớp và biến `small` được khởi tạo. Với `128`, pattern không khớp, vì chuyển đổi sang `byte` không thể giữ nguyên giá trị. Không có phép ép kiểu mất dữ liệu nào được thực hiện để trả về một kết quả sai.

Testing conversion có thể bao gồm widening, narrowing, boxing, unboxing và một số tổ hợp chuyển đổi tham chiếu/primitive. Tuy nhiên, việc một chuyển đổi có thể được kiểm tra không có nghĩa mọi giá trị đều chuyển đổi chính xác. Runtime xác định tính chính xác dựa trên giá trị cụ thể.

Ví dụ:

| Phép chuyển đổi | Kết quả kiểm tra |
|---|---|
| `byte` sang `int` | Luôn chính xác |
| `float` sang `double` | Luôn chính xác đối với giá trị `float` đang có |
| `int` sang `byte` | Chỉ chính xác nếu giá trị nằm trong miền `byte` |
| `int` sang `float` | Có thể mất độ chính xác với số nguyên lớn |
| `float` sang `int` | Chỉ chính xác khi giá trị có thể chuyển thành số nguyên mà không mất thông tin |
| `double` sang `long` | Có thể mất phần thập phân, vượt miền hoặc mất thông tin đặc biệt |

Đặc biệt, chuyển đổi từ số dấu phẩy động sang kiểu nguyên không chính xác với `NaN`, vô cực hoặc số âm không (`-0.0`), vì phép chuyển đổi có thể làm mất thông tin. Khi cần kiểm tra dữ liệu tài chính, đo lường hoặc giới hạn miền số, hãy hiểu rõ quy tắc chuyển đổi và không thay thế kiểm tra nghiệp vụ bằng một phép ép kiểu.

## 5. Dùng primitive pattern trong record pattern

Record pattern có thể kiểm tra kiểu thành phần của record, kể cả khi kiểu được khai báo và kiểu pattern khác nhau. Ví dụ:

    record Cup(double volume) { }

    static void inspectCup(Cup cup) {
        if (cup instanceof Cup(double value)) {
            System.out.println("double: " + value);
        }

        if (cup instanceof Cup(float value)) {
            System.out.println("Có thể chuyển chính xác sang float: " + value);
        }

        if (cup instanceof Cup(int value)) {
            System.out.println("Có thể chuyển chính xác sang int: " + value);
        }
    }

    // Giá trị float được mở rộng chính xác thành double khi truyền vào record.
    Cup cup = new Cup(34.567f);
    inspectCup(cup);

Thành phần `volume` có kiểu `double`. Pattern `Cup(double value)` luôn khớp với record không null. Pattern `Cup(float value)` chỉ khớp nếu giá trị `double` có thể biểu diễn chính xác bằng `float`. Pattern `Cup(int value)` chỉ khớp nếu giá trị là số nguyên có thể biểu diễn chính xác bằng `int`.

Trong ví dụ, `34.567f` được mở rộng thành `double` khi tạo record. Vì giá trị `double` đó bắt nguồn từ một `float`, pattern `float` có thể chuyển đổi chính xác trở lại. Pattern `int` không khớp do giá trị có phần thập phân.

Với record component là wrapper, primitive pattern có thể cần unboxing. Nếu component là `null`, primitive pattern không khớp. Hãy xử lý trường hợp null rõ ràng nếu dữ liệu đầu vào cho phép null.

## 6. Dùng primitive selector và when trong switch

Java 27 preview cho phép selector của switch dùng các primitive types. Các nhãn case có thể là hằng cùng kiểu, primitive type pattern hoặc guarded pattern có `when`.

Ví dụ phân loại điểm đánh giá dạng `double`:

    static String toRating(double rating) {
        return switch (rating) {
            case 0d -> "0 sao";
            case double value when value > 0d && value < 2.5d
                -> "Chưa tốt";
            case double value when value >= 2.5d && value < 5d
                -> "Khá";
            case 5d -> "Tốt nhất";
            default -> "Ngoài miền đánh giá";
        };
    }

Ở đây:

- `case 0d` khớp giá trị bằng không.
- Pattern `double value` bắt giá trị selector và đưa vào biến `value`.
- `when` giới hạn miền giá trị được nhãn pattern chấp nhận.
- `default` xử lý các giá trị còn lại, bao gồm giá trị âm, lớn hơn 5 và `NaN`.

Với selector `long`, `float` hoặc `double`, hằng trong nhãn `case` phải phù hợp kiểu selector hoặc kiểu wrapper tương ứng. Ví dụ switch trên `float` dùng `0f`, `2.5f`; switch trên `double` dùng `0d`, `2.5d`. Không trộn hằng nguyên với hằng dấu phẩy động tùy tiện, vì việc chuyển đổi ngầm có thể làm thay đổi độ chính xác.

Pattern không có guard có thể chi phối (dominate) các pattern phía sau nếu mọi giá trị khớp với pattern sau cũng chắc chắn khớp với pattern trước. Ví dụ:

    static void example(float value) {
        switch (value) {
            case int whole ->
                System.out.println("Số nguyên: " + whole);
            // case byte small -> // Compile-time error: bị pattern int chi phối
            //     System.out.println(small);
            default ->
                System.out.println("Giá trị khác");
        }
    }

Mọi giá trị có thể chuyển đổi chính xác từ `float` sang `byte` cũng nằm trong tập giá trị có thể chuyển đổi chính xác sang `int`. Vì vậy, pattern `int` đứng trước sẽ chi phối pattern `byte`. Compiler phát hiện trường hợp không thể tới được để tránh nhánh mã vô nghĩa.

## 7. Biên dịch và chạy đúng JDK 27

Vì tính năng đang là preview của Java 27, cả compiler và runtime đều phải dùng JDK 27. Kiểm tra trước:

    java --version
    javac --version
    Get-Command java, javac -All | Select-Object Name, Source

Hai lệnh `java` và `javac` cần trỏ đến JDK 27. Nếu máy có nhiều JDK, kiểm tra cả đường dẫn executable và cấu hình toolchain của IDE/build tool.

Biên dịch ví dụ bằng:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/PrimitiveTypePatterns.java

Chạy bằng:

    java --enable-preview -cp out PrimitiveTypePatterns

Hai cờ có ý nghĩa khác nhau:

- `--release 27` chọn bộ quy tắc ngôn ngữ, bytecode và API của Java 27.
- `--enable-preview` cho phép compiler chấp nhận tính năng preview của release đó.
- Khi chạy, `java --enable-preview` cho phép JVM nạp class phụ thuộc preview của JDK 27.

Nếu chỉ bật preview khi biên dịch mà quên lúc chạy, JVM từ chối class file phụ thuộc preview. Nếu compiler hoặc runtime dùng release khác, kết quả cũng không hợp lệ. Class file phụ thuộc preview được gắn với release tạo ra nó; không thể lấy class file preview Java 27 rồi chạy trên JDK 26 hoặc JDK 28 chỉ bằng cách bật preview.

Với Gradle, toolchain và compiler/test runtime phải cùng nhắm JDK 27. Ví dụ Groovy DSL cho một dự án thử nghiệm:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(27)
        }
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 27
        options.compilerArgs.add("--enable-preview")
    }

    tasks.withType(Test).configureEach {
        jvmArgs("--enable-preview")
    }

    tasks.withType(JavaExec).configureEach {
        jvmArgs("--enable-preview")
    }

Chỉ thêm các cờ preview vào source set hoặc task thực sự cần thử tính năng. Phiên bản Gradle wrapper phải hỗ trợ JDK 27. Cấu hình JDK của IDE, Gradle daemon, compiler toolchain, test worker và ứng dụng chạy cần được kiểm tra riêng.

## 8. Thực hành theo quy trình có thể tái hiện

Thực hiện các bước sau trong một thư mục thử nghiệm riêng:

1. Cài JDK 27 và xác nhận `java --version`, `javac --version` đều báo release 27.
2. Tạo lớp `PrimitiveTypePatterns` chứa các ví dụ `instanceof`, safe casting, record patterns và primitive switch.
3. Biên dịch bằng `javac --enable-preview --release 27`.
4. Chạy bằng `java --enable-preview` từ cùng JDK 27.
5. Thử các giá trị biên như `127`, `128`, `16_777_217`, `NaN`, vô cực và `-0.0` để quan sát phép chuyển đổi chính xác.
6. Thử thay đổi thứ tự case pattern để nhận diện lỗi dominance do compiler phát hiện.
7. Ghi lại JDK release, JEP, cờ compile/run và kết quả quan sát để có thể tái tạo thử nghiệm.
8. Xóa thư mục output và biên dịch lại khi đổi JDK hoặc thay đổi release preview.

Một bài thực hành tốt phải chỉ ra được giá trị nào khớp pattern, vì sao phép chuyển đổi chính xác hoặc mất thông tin, và compiler/runtime cần những cờ nào. Không kết luận tính năng đã ổn định chỉ vì chương trình chạy thành công trên JDK 27.

## 9. Quyết định sử dụng sau thông báo rút tính năng

Ngày 11-11-2026, nhóm Java thông báo ngừng phát triển Primitive Types in Patterns, `instanceof`, and `switch`. Draft JEP 8393282 cho preview thứ sáu sẽ bị rút và tính năng được thông báo sẽ bị loại khỏi JDK 28.

Điều đó tạo ra ranh giới sử dụng rõ ràng:

- **JDK 27:** có thể thực hành với JEP 532 fifth preview bằng cờ preview và đúng JDK 27.
- **JDK 26:** có JEP 530 fourth preview; không dùng mã preview Java 27 thay thế cho cấu hình release 26.
- **JDK 28:** không tiếp tục dựa vào primitive patterns; tính năng đã được thông báo sẽ bị loại khỏi release này.
- **Mã sản phẩm:** không đưa primitive patterns preview vào API công khai, thư viện dùng chung hoặc nhánh phát hành cần nâng cấp liên tục. Nếu đã thử nghiệm, giữ mã trong nhánh riêng và có phương án viết lại bằng cú pháp Java ổn định hiện có.

Việc một tính năng đã xuất hiện trong nhiều lần preview không bảo đảm nó sẽ trở thành final. Trước khi dùng bất kỳ preview nào, hãy kiểm tra trạng thái mới nhất của JEP, release notes và Java Language Specification. Nếu tính năng đã bị rút, hãy cập nhật kế hoạch kỹ thuật thay vì tiếp tục dựa trên ví dụ từ tài liệu cũ.

## Tài liệu chính thức

- [Oracle — Java Language Changes by Release 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): xác nhận JEP 532 là lần preview thứ năm của Java 27 và không có thay đổi đáng kể so với các lần trước.
- [Oracle — Primitive Types in Patterns, instanceof, and switch (Java 27)](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html): tổng quan các ngữ cảnh primitive patterns, `instanceof`, switch, record patterns và when clauses.
- [Java Language Specification 27 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html): đặc tả chính xác testing conversions, primitive patterns, switch compatibility và dominance.
- [Oracle — Preview Features (Java 27)](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): cách bật preview ở compiler/runtime và giới hạn tương thích giữa các release.
- [Oracle — JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): ngày phát hành JDK 27 và danh sách tính năng preview.
- [Oracle — Java Language Changes by Release 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): đối chiếu JEP 530 fourth preview của Java 26.
- [Inside Java — Withdrawing the Primitive Patterns Preview Feature](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/): thông báo ngày 11-11-2026 về việc dừng phát triển, rút đề xuất preview thứ sáu và loại tính năng khỏi JDK 28.

Nội dung và trạng thái được đối chiếu theo tài liệu Java SE 26/27 và thông báo của nhóm Java tại ngày 27-11-2026. Đây là bài thực hành preview trên JDK 27, không phải khuyến nghị sử dụng primitive patterns cho sản phẩm mới.
