# Biên dịch và thực hành các kiến thức Java 5 trên JDK còn được hỗ trợ

## 1. Học tính năng bắt đầu từ Java 5 không có nghĩa phải dùng JDK 5

Các kiến thức như generics, enum, annotation, boxing/unboxing, vòng lặp nâng cao, varargs và static import vẫn được dùng trong mã Java hiện đại. Có thể học cơ chế của chúng trên một JDK đang được duy trì.

Cần tách ba câu hỏi:

1. Tính năng ngôn ngữ đang học là gì?
2. Công cụ `javac` đang chạy thuộc JDK nào?
3. Mã được biên dịch để dùng phiên bản Java nào?

Bài này chọn **Java 21 làm mức biên dịch và chạy chính**. Mục tiêu là dùng những kiến thức gắn với Java 5 trong một chương trình hiện đại có thể kiểm chứng, không tái tạo môi trường runtime cũ.

Với môi trường học mới, chọn bản cập nhật đang được nhà phân phối duy trì trong dòng JDK phù hợp. Không suy ra “còn được hỗ trợ” chỉ từ nhãn LTS hoặc từ việc một bộ cài vẫn tải được. Các nhà phân phối công bố thời hạn và điều kiện khác nhau; chẳng hạn [lộ trình Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/support) công bố lịch cho các dòng 21 và 25, còn [lộ trình Oracle Java SE](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) có phạm vi hỗ trợ riêng của Oracle.

Không cần hạ mức biên dịch xuống Java 5 để học các tính năng này. Việc một nguồn mã tương thích lịch sử với trình biên dịch Java 5 là một mục tiêu khác, không thuộc bài thực hành này.

## 2. Kiểm tra công cụ thực sự đang được dùng

Chạy trong terminal:

```shell
java -version
javac -version
```

Cần quan sát:

- Có cả `java` để chạy và `javac` để biên dịch không?
- Hai lệnh có đang trỏ tới JDK dự định sử dụng không?
- Phiên bản cập nhật có phù hợp chính sách duy trì của môi trường không?

Một máy có thể cài nhiều JDK. IDE dùng JDK 21 nhưng terminal lại gọi JDK khác là tình huống hoàn toàn có thể xảy ra. `JAVA_HOME`, thứ tự `PATH`, cấu hình IDE và công cụ build là các nơi cần đối chiếu; không chỉ nhìn một màn hình cài đặt rồi kết luận mọi lệnh đều dùng cùng JDK.

Trên PowerShell, có thể xem đường dẫn được chọn:

```powershell
Get-Command java, javac | Select-Object Name, Source
```

Nếu đường dẫn chứa khoảng trắng hoặc có nhiều bộ cài, có thể gọi trực tiếp công cụ từ JDK đã chọn bằng cú pháp phù hợp shell. Không cần thay đổi cấu hình hệ thống chỉ để chạy một ví dụ độc lập nếu đã xác định được bộ công cụ cần dùng.

Bài sử dụng JDK đầy đủ. Không chỉ có runtime mà thiếu compiler.

## 3. Hiểu javac, java và tệp đầu ra

Luồng biên dịch tường minh:

```text
Java5OnModernJdk.java
        ↓ javac
Các tệp .class trong thư mục out
        ↓ java -cp out Java5OnModernJdk
Chạy main và kiểm tra kết quả
```

- Tệp `.java` chứa mã nguồn.
- `javac` kiểm tra nguồn và tạo các tệp lớp.
- `java` khởi chạy chương trình từ lớp đã biên dịch.
- Class path cho biết nơi tìm các lớp và tài nguyên liên quan.

Tên tệp phải khớp với lớp `public` của ví dụ. Khi chạy lớp đã biên dịch, dùng tên lớp, không thêm `.class`.

Phương thức bắt đầu của bài dùng dạng quen thuộc:

```java
public static void main(String[] args)
```

Cách chạy hai bước được chọn để nhìn rõ lỗi xảy ra ở bước biên dịch hay bước chạy. Các tiện ích chạy mã nguồn khác không làm hai khái niệm ấy trở thành một. Xem quy tắc công cụ tại [javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) và [java](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

## 4. Chọn --release theo nền tảng đích hiện tại

Lệnh chính của bài:

```shell
javac --release 21 -encoding UTF-8 -Xlint:all -Werror -d out Java5OnModernJdk.java
```

Ý nghĩa:

| Tùy chọn | Mục đích |
| --- | --- |
| `--release 21` | Dùng quy tắc ngôn ngữ, mức lớp đầu ra và API nền tảng tương ứng với Java 21 mà compiler hỗ trợ |
| `-encoding UTF-8` | Đọc mã nguồn theo UTF-8 |
| `-Xlint:all` | Bật các nhóm cảnh báo lint của compiler |
| `-Werror` | Cho lần biên dịch thất bại nếu có cảnh báo |
| `-d out` | Đặt lớp biên dịch vào thư mục đầu ra riêng |

`--release` hữu ích khi dùng một compiler mới hơn nhưng muốn giữ mức nền tảng đích được chỉ định. Các mức release hợp lệ tùy compiler; dùng `javac --help` để xem, không tự giả định mọi compiler hiện đại hỗ trợ mọi release trong lịch sử.

Không dùng `--source`/`--target` như cách thay thế đầy đủ cho kiểm soát API nền tảng của `--release`. Chỉ tạo bytecode ở một mức không tự ngăn nguồn gọi API mới hơn nếu môi trường biên dịch vẫn nhìn thấy chúng.

`--release 21` cũng **không giới hạn nguồn chỉ được dùng tính năng xuất hiện ở Java 5**. Nó cho phép những gì thuộc mức Java 21; việc bài đang tập trung vào nhóm tính năng nào là phạm vi học tập, không phải một chế độ compiler lịch sử.

Ví dụ không dùng preview, nên không cần `--enable-preview`.

## 5. Một bài thực hành kết hợp các tính năng còn sử dụng

Bài toán:

- Giữ ba điểm số 80, 55, 90 trong danh sách có kiểu.
- Duyệt và tính tổng.
- Dùng enum biểu diễn kết quả thay cho chuỗi tùy ý.
- Dùng một generic method lấy phần tử đầu.
- Dùng varargs để cộng một số lượng số nguyên tùy ý.
- Dùng static import cho một hàm toán.
- Gắn annotation có thể đọc lúc chạy.
- Kiểm tra các kết quả đã dự đoán.

Bảng nhận diện:

| Thành phần trong mã | Kiến thức được thực hành |
| --- | --- |
| `List<Integer>` | Generics ràng buộc kiểu phần tử |
| `scores.add(80)` | Boxing từ `int` sang `Integer` |
| `total += score` | Unboxing khi dùng phần tử trong phép tính |
| `for (Integer score : scores)` | Vòng lặp nâng cao |
| `enum Result` | Tập giá trị được đặt tên và kiểm tra kiểu |
| `<T> T first(List<T> values)` | Phương thức tổng quát |
| `sum(int... values)` | Tham số varargs |
| `import static java.lang.Math.max` | Static import |
| `@PracticeInfo` | Metadata gắn vào lớp |
| `@Retention(RUNTIME)` | Cho metadata tồn tại để đọc lúc chạy |

Mục đích là nhận diện cơ chế và có bằng chứng chạy, chưa thay thế bài chuyên sâu của từng tính năng. Ví dụ không dùng collection không khai báo kiểu, không tắt cảnh báo và không dùng API đã bị loại bỏ.

## 6. Mã hoàn chỉnh

Lưu vào `Java5OnModernJdk.java`:

```java
import static java.lang.Math.max;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.ArrayList;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface PracticeInfo {
    String value();
}

@PracticeInfo("java5-on-current-jdk")
public class Java5OnModernJdk {
    enum Result {
        PASS, RETRY
    }

    private static int checks;

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        checks++;
    }

    private static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    private static int sum(int... values) {
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<Integer>();
        scores.add(80);
        scores.add(55);
        scores.add(90);

        int total = 0;
        for (Integer score : scores) {
            total += score;
        }

        Result result = total >= 180 ? Result.PASS : Result.RETRY;
        PracticeInfo info =
                Java5OnModernJdk.class.getAnnotation(PracticeInfo.class);
        check(scores.size() == 3, "Generic list size");
        check(first(scores) == 80, "Generic method and unboxing");
        check(total == 225, "Enhanced loop total");
        check(sum(1, 2, 3) == 6, "Varargs with values");
        check(sum() == 0, "Varargs with zero values");
        check(max(80, 55) == 80, "Static import");
        check(result == Result.PASS, "Enum value");
        check(info != null && info.value().equals("java5-on-current-jdk"),
                "Runtime annotation");

        System.out.println("scores=" + scores);
        System.out.println("first=" + first(scores));
        System.out.println("total=" + total);
        System.out.println("result=" + result);
        System.out.println("sum=" + sum(1, 2, 3));
        System.out.println("max=" + max(80, 55));
        System.out.println("annotation=" + info.value());
        System.out.println("PASS checks=" + checks);
    }
}
```

`PracticeInfo` là annotation interface phụ trợ cùng tệp; lớp `public` vẫn là `Java5OnModernJdk`. Compiler có thể tạo nhiều tệp `.class` từ một tệp nguồn, kể cả kiểu enum lồng trong lớp. Cần giữ toàn bộ đầu ra cần thiết trong class path, không chỉ chép riêng một tệp lớp chính rồi bỏ các kiểu phụ.

Annotation không tự làm tổng điểm thay đổi. Nó là metadata; trong ví dụ, mã gọi `getAnnotation` để đọc giá trị. `@Retention(RUNTIME)` thể hiện chính sách cần cho phép đọc lúc chạy. Cú pháp và các quy tắc annotation được mô tả tại [JLS, chương Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html).

## 7. Biên dịch và chạy đúng hai bước

Tại thư mục chứa mã nguồn, dùng các lệnh:

```shell
javac --release 21 -encoding UTF-8 -Xlint:all -Werror -d out Java5OnModernJdk.java
java -cp out Java5OnModernJdk
```

Chỉ chạy lệnh thứ hai khi biên dịch thành công. Nếu terminal vẫn có các tệp lớp từ lần trước, chạy sau một lần biên dịch thất bại có thể vô tình thực thi mã cũ; cần quan sát kết quả compiler thay vì chỉ nhìn stdout của một lệnh sau đó.

Stdout mong đợi:

```text
scores=[80, 55, 90]
first=80
total=225
result=PASS
sum=6
max=80
annotation=java5-on-current-jdk
PASS checks=8
```

Hàm `check` chủ động ném `AssertionError` nếu kết quả sai, nên không cần cờ `-ea`. Tám lần kiểm tra xác nhận kích thước danh sách, kết quả generic method, tổng vòng lặp, varargs có/không có đối số, static import, enum và annotation.

Cần phân biệt dòng `result=PASS` của bài toán tổng điểm với dòng `PASS checks=8` của các ca kiểm tra. Chúng có hai vai trò khác nhau.

### Vì sao first(scores) == 80 không phải lỗi so tham chiếu?

Trong biểu thức này, một vế là `Integer` còn vế kia là `int`; phép so kích hoạt unboxing và so số nguyên. Đây không phải quy tắc “mọi hai Integer đều có thể so giá trị bằng ==”.

Nếu so hai tham chiếu wrapper để kiểm tra giá trị, phải chọn phép so phù hợp và xử lý `null` theo hợp đồng. Các quy tắc boxing/unboxing nằm trong [JLS, chương Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html).

## 8. Thử âm: an toàn kiểu phải được compiler chứng minh

Một bài thực hành tốt có cả trường hợp cố ý bị từ chối. Lưu đoạn sau thành tệp riêng `WrongType.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WrongType {
    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<Integer>();
        scores.add("not an integer");
    }
}
```

Chạy riêng:

```shell
javac --release 21 -encoding UTF-8 -d out-negative WrongType.java
```

**Kết quả mong đợi: biên dịch thất bại**, vì không thể thêm `String` vào `List<Integer>`. Nội dung thông báo và cách trình bày chẩn đoán có thể khác giữa compiler hoặc ngôn ngữ hiển thị; tiêu chí là lỗi không tương thích kiểu được phát hiện.

Không cố chạy `WrongType` như một chương trình hợp lệ. Không đưa tệp cố ý sai này vào lần biên dịch của bài chính rồi kết luận ví dụ chính hỏng.

Cũng không sửa bằng cách bỏ kiểu phần tử hoặc thêm `@SuppressWarnings`. Điều đang cần chứng minh chính là compiler ngăn dữ liệu không phù hợp.

Sau phép thử âm, giữ hoặc xóa tệp theo cách tổ chức bài tập; nếu giữ, nên đặt riêng những bài được thiết kế để không biên dịch.

## 9. Kiểm tra hành vi lúc chạy, không chỉ cú pháp

Sau khi bản gốc chạy đúng, thay **một yếu tố mỗi lần** rồi dự đoán kết quả:

| Thay đổi | Dự đoán cần kiểm chứng |
| --- | --- |
| Thêm điểm 40 | size = 4, total = 265; điều chỉnh ca mong đợi tương ứng |
| Đổi ngưỡng kết quả từ 180 thành 230 | Với tổng 225, result = RETRY |
| Gọi `sum()` | Tổng bằng 0 |
| Gọi `sum(new int[] {4, 5})` | Tổng bằng 9 |
| Gọi `first` với danh sách rỗng | `IllegalArgumentException` theo hợp đồng hàm |
| Bỏ `RetentionPolicy.RUNTIME` theo chính sách khác | Không còn được giả định đọc annotation lúc chạy như bản gốc |
| Chèn `null` vào danh sách điểm rồi tính tổng | Unboxing có thể gây `NullPointerException`; cần quyết định hợp đồng dữ liệu |

Một lần compiler chấp nhận không chứng minh mọi đầu vào đều an toàn. Generics ràng buộc kiểu phần tử nhưng không tự loại bỏ mọi `null`, không bảo đảm danh sách không rỗng và không quyết định chính sách điểm hợp lệ.

Khi cố ý tạo ca lỗi lúc chạy, hãy bắt đúng loại lỗi trong một kiểm tra riêng hoặc quan sát chương trình thất bại có chủ đích. Đừng bắt mọi `Exception` rồi in PASS mà không xác nhận điều gì đã xảy ra.

## 10. IDE và công cụ build phải dùng cùng ý định biên dịch

Sau khi chạy được bằng terminal, có thể đưa bài vào IDE hoặc công cụ build. Cần đồng bộ ba phần:

1. JDK dùng cho công cụ biên dịch.
2. Mức ngôn ngữ/API đích.
3. JVM dùng để chạy hoặc kiểm thử.

Một IDE có thể hiển thị mã không lỗi trong khi công cụ build dùng cấu hình khác. Ngược lại, terminal có thể biên dịch đúng nhưng nút Run của IDE chọn runtime không phù hợp.

Nếu dùng Gradle, phân biệt JVM chạy Gradle với Java toolchain dùng biên dịch/kiểm thử và mức release đầu ra. Với dự án có quy ước sẵn, làm theo cấu hình hiện hành của dự án; không thêm một cấu hình riêng chỉ để ghi “Java 5” trong bài học.

Ví dụ độc lập này không cần plugin ngoài, không cần tạo dự án Spring và không cần bật tính năng tự sinh của một repository lớn. Có thể hoàn thành toàn bộ kiểm chứng bằng JDK được chọn.

`--release` không hạ cấp thư viện bên ngoài, không kiểm tra mọi phụ thuộc native và không tự chạy chương trình trên runtime đích. Khi có thư viện thật, cần kiểm tra cả các phụ thuộc và chạy thử trên môi trường được triển khai.

## 11. Chẩn đoán các lỗi môi trường thường gặp

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| Không tìm thấy `javac` | JDK đã được cài và đường dẫn compiler có đúng không? |
| `java -version` khác dự định | Xem đường dẫn lệnh, `PATH` và cấu hình terminal |
| `release version 21 not supported` | Compiler đang dùng quá cũ hoặc không phải bộ dự định; kiểm tra `javac -version` |
| Lớp public phải nằm trong tệp khác | Đổi đúng tên tệp hoặc tên lớp theo ví dụ |
| Không tìm thấy lớp chính | Đang dùng đúng thư mục, class path và tên lớp chưa? |
| `UnsupportedClassVersionError` | Runtime đang chạy không hỗ trợ mức lớp đã biên dịch |
| Mã sửa nhưng stdout không đổi | Lần biên dịch mới có thành công không, hay đang chạy lớp cũ? |
| Cảnh báo làm build thất bại | Đọc cảnh báo do `-Werror`, sửa nguyên nhân thay vì tắt hàng loạt |
| Không tìm thấy annotation khi chạy | Kiểm tra retention và việc giữ các lớp phụ trợ cần thiết |
| Chạy chính thành công nhưng biên dịch tất cả thất bại | Có vô tình đưa tệp thử âm vào cùng tập nguồn không? |

Không giải quyết lỗi class path bằng cách di chuyển tệp ngẫu nhiên cho đến khi chạy. Hãy xác định compiler ghi lớp ở đâu và launcher đang tìm lớp ở đâu.

Không dùng các tùy chọn cũ không còn được compiler hỗ trợ để ép mô phỏng một runtime lịch sử. Đích của bài là kiến thức còn được dùng và một chu trình biên dịch/chạy hiện đại có thể tái lập.

## 12. Tiêu chí hoàn thành bài thực hành

Một lượt thực hành được xem là có bằng chứng khi:

- Đã xác định rõ `java` và `javac` được dùng.
- Compiler và runtime thuộc dòng JDK được chọn; trạng thái duy trì được đối chiếu với nhà phân phối.
- Mã chính biên dịch thành công với mức release đã công bố, không cảnh báo bị bỏ qua.
- Chương trình chạy và khớp stdout cùng tám kiểm tra.
- Tệp thử âm bị compiler từ chối đúng lý do.
- Người học giải thích được mỗi tính năng đang thể hiện ở dòng nào.
- Không nhầm tính năng có nguồn gốc ở Java 5 với việc yêu cầu cài môi trường cũ.
- Nếu thay dữ liệu, kết quả mong đợi được cập nhật từ phân tích bài toán trước khi chạy.

Không cần một bảng phiên bản dài để bắt đầu. Điều quan trọng là có môi trường hiện hành, phạm vi bài rõ và chu trình thử thành công/thất bại có chủ đích.

## 13. Bài tập tiếp theo

1. **Tách `PracticeInfo` thành tệp riêng.** Biên dịch cả hai nguồn trong cùng lệnh và giữ đúng class path. Stdout không đổi.

2. **Thêm một generic method lấy phần tử cuối.** Công bố hành vi với danh sách rỗng; không trả `null` âm thầm nếu hợp đồng yêu cầu báo lỗi.

3. **Thêm một giá trị enum mới.** Cập nhật một quy tắc sử dụng nó và kiểm tra hành vi, thay vì chỉ in tên enum.

4. **Tạo hai ca compile-fail khác nhau.** Một ca truyền sai kiểu vào generic method, một ca gọi sai số lượng/kiểu tham số. Giữ chúng tách khỏi nguồn chạy thành công.

5. **Chạy cùng bài bằng một JDK hiện đại khác có hỗ trợ `--release 21`.** Giữ mức đích và stdout. Sau đó giải thích vì sao điều này kiểm tra công cụ mới chạy bài, không chứng minh đã kiểm thử trên mọi runtime hay mọi thư viện có thể có.

Học các kiến thức Java 5 còn hữu ích có thể đi cùng công cụ đang được duy trì. Giữ rõ mức biên dịch, môi trường chạy và kết quả mong đợi sẽ giúp tập trung vào cơ chế của tính năng thay vì các vấn đề của một nền tảng cũ.
