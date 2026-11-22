# Kiến thức Java cần có trước khi học các tính năng Java 5

## 1. Học Java 5 trong môi trường Java hiện đại cần nền tảng nào?

Nhóm tính năng gắn với Java 5 như kiểu tổng quát (generics), kiểu liệt kê (enum), chú thích mã (annotation), tự đóng/mở gói kiểu nguyên thủy (autoboxing/unboxing), vòng lặp nâng cao và tham số số lượng biến đổi vẫn xuất hiện trong mã Java hiện đại. Muốn hiểu chúng, cần nắm những khái niệm mà chúng xây dựng lên: kiểu, đối tượng, phương thức, mảng, quan hệ kiểu và luồng thực thi.

Điều kiện trước khi học không phải là thuộc toàn bộ ngôn ngữ hay đọc hết một thư viện. Người học cần làm được ba việc:

1. Đọc một chương trình nhỏ và dự đoán nó xử lý dữ liệu ra sao.
2. Giải thích kiểu dữ liệu và đối tượng đang được sử dụng.
3. Nhận biết lỗi được phát hiện khi biên dịch và lỗi chỉ xuất hiện khi chạy.

Bài này chỉ chọn kiến thức còn dùng trong Java hiện đại. Các ví dụ chạy trên JDK hiện đại; không cần cài JDK 5 hoặc học một bộ API cũ trước rồi mới tiếp cận kiến thức còn áp dụng.

Đừng biến chính nội dung sắp học thành điều kiện tiên quyết. Chẳng hạn, trước khi học generics, cần hiểu kiểu và quan hệ kiểu; chưa cần hiểu sẵn wildcard hoặc xóa kiểu.

## 2. Bản đồ điều kiện tiên quyết và tính năng sẽ học

| Nền tảng cần có | Nó giúp hiểu phần nào? | Mức cần trước khi bắt đầu |
| --- | --- | --- |
| Kiểu nguyên thủy, kiểu tham chiếu, `null` | Boxing/unboxing, generics và lỗi kiểu | Phân biệt được giá trị và tham chiếu |
| Biến, phép gán, toán tử | Biểu thức, chuyển đổi và vòng lặp | Đọc được biểu thức đơn giản |
| Điều kiện, vòng lặp cơ bản | Vòng lặp nâng cao và cách duyệt dữ liệu | Tự viết được vòng lặp theo chỉ số |
| Mảng | Varargs và duyệt phần tử | Biết kiểu phần tử, độ dài, chỉ số |
| Phương thức | Generic method, varargs, overload | Phân biệt tham số, đối số, giá trị trả về |
| Lớp, đối tượng, hàm dựng | Generics, enum và mô hình đối tượng | Tạo và sử dụng được một lớp nhỏ |
| Giao diện, kế thừa, ghi đè, đa hình | Ràng buộc kiểu, collection và chiến lược xử lý | Hiểu kiểu biến khác kiểu đối tượng |
| `equals`, `==` và `Object` | Collection, wrapper và so sánh giá trị | Biết hai phép so không cùng mục đích |
| Ngoại lệ và đọc lỗi | An toàn kiểu, đầu vào sai, tác vụ thất bại | Phân biệt lỗi biên dịch với ngoại lệ |
| Package, import và cách đọc API | Static import, annotations và thư viện | Biết tìm đúng kiểu/phương thức |
| Khái niệm collection | Generics và vòng lặp nâng cao trên tập phần tử | Biết collection giải quyết việc gì |
| Tác vụ, luồng, trạng thái dùng chung | Các API đồng thời khi học đến phần đó | Chỉ cần bổ sung trước nhánh đồng thời |

Không cần học tất cả ở cùng mức sâu. Các mục về kiểu, phương thức, mảng và mô hình đối tượng là nền chung; kiến thức luồng chỉ trở thành điều kiện trực tiếp khi đi vào xử lý đồng thời.

## 3. Kiểu dữ liệu: phân biệt giá trị nguyên thủy và tham chiếu

### 3.1. Kiểu nguyên thủy

Các kiểu như `int`, `long`, `double`, `boolean` dùng cho những giá trị nguyên thủy. Cần hiểu:

- Kiểu quyết định miền giá trị và phép toán được phép.
- Phép chia số nguyên khác phép chia số thực.
- Gán một kiểu rộng hơn cho kiểu hẹp hơn có thể cần chuyển đổi rõ và có thể mất dữ liệu.
- Một biến `int` không mang giá trị `null`.

Chưa cần thuộc mọi giá trị giới hạn của mọi kiểu, nhưng phải biết số không tự biến thành đối tượng chỉ vì được dùng trong mã Java.

Nền này giúp hiểu vì sao có các lớp bao như `Integer`, và vì sao tự chuyển đổi giữa `int` với `Integer` cần chú ý `null`. Cơ chế tự chuyển đổi là nội dung cần học tiếp, không phải điều phải thuộc trước.

### 3.2. Kiểu tham chiếu

Biến có kiểu lớp, giao diện hoặc mảng giữ một tham chiếu tới đối tượng hoặc `null`. Cần phân biệt:

```java
// Đoạn minh họa bên trong một phương thức.
String text = "Java";
String same = text;
String missing = null;
```

`same` không phải “bản sao độc lập của mọi dữ liệu bên trong text”; hai biến đang cùng tham chiếu một đối tượng. `missing` chưa trỏ tới đối tượng `String` nào.

Điều này liên quan trực tiếp tới collection chứa đối tượng, wrapper có thể thiếu giá trị, chia sẻ đối tượng và các biến được truyền vào phương thức.

Hệ thống kiểu và sự khác nhau giữa biến nguyên thủy/tham chiếu được mô tả tại [JLS, chương Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html).

### 3.3. Kiểu tĩnh và đối tượng lúc chạy

Trình biên dịch dựa vào kiểu khai báo để kiểm tra một phép gọi. Đối tượng thực tế vẫn có lớp riêng khi chương trình chạy.

Ví dụ chương trình phía dưới có biến `Named first` tham chiếu tới đối tượng `Learner`. Qua biến đó, ta gọi được hành vi do `Named` khai báo; không vì đối tượng là `Learner` mà mọi phương thức riêng của `Learner` tự xuất hiện trên kiểu `Named`.

Đây là nền tảng quan trọng để học generics mà không nhầm “tên kiểu ghi trong mã” với “mọi thứ có thể nằm trong một đối tượng”.

## 4. Biểu thức, điều kiện và vòng lặp cơ bản

Người học nên tự viết được:

- `if/else` cho một điều kiện.
- Vòng `for` có biến chỉ số hoặc `while`.
- Biến tích lũy như tổng hoặc số lượng.
- `return` để trả kết quả.
- Các toán tử so sánh, logic và tăng biến cơ bản.

Một ví dụ đủ để kiểm tra mức hiểu là duyệt mảng điểm, cộng tổng và đếm phần tử lớn hơn hoặc bằng một ngưỡng.

Với biểu thức `name == null || name.isBlank()`, cần biết `||` có đánh giá ngắn mạch: nếu vế đầu đúng, vế sau không được gọi. Nhờ vậy, chương trình không gọi phương thức trên `null`.

Trước khi học vòng lặp nâng cao, cần hiểu việc duyệt từng phần tử đang làm gì. Không chỉ ghi nhớ cú pháp ngắn hơn mà bỏ qua ý nghĩa biến vòng lặp, phần tử và tác dụng phụ.

Các quy tắc điều kiện/vòng lặp và biểu thức vẫn thuộc ngôn ngữ hiện tại; có thể đối chiếu [JLS, chương Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html) và [JLS, chương Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html).

## 5. Mảng và phương thức: nền cho duyệt dữ liệu và varargs

### 5.1. Mảng

Cần biết:

- `int[]` và `Learner[]` là các kiểu mảng có kiểu phần tử xác định.
- Độ dài mảng được xác định khi tạo.
- Chỉ số hợp lệ đi từ 0 đến `length - 1`.
- Mảng rỗng có `length == 0`, khác với biến mảng là `null`.
- Truy cập phần tử của mảng đối tượng có thể nhận một tham chiếu, không tự tạo đối tượng mới.

Khi thấy `learners[i].score()`, người học phải hiểu hai bước: lấy đối tượng ở vị trí i, rồi gọi phương thức trên đối tượng đó.

Đây là nền để hiểu tham số varargs có quan hệ với mảng và để hiểu vòng lặp nâng cao. Chưa cần đi sâu vào mọi quy tắc tương tác giữa mảng với generics ngay ở bước chuẩn bị.

### 5.2. Phương thức

Phải phân biệt được:

| Khái niệm | Ví dụ |
| --- | --- |
| Tên phương thức | `sum` |
| Tham số khai báo | `int[] values` |
| Đối số tại nơi gọi | `scores` trong `sum(scores)` |
| Kiểu trả về | `int` |
| Giá trị trả về | Tổng điểm đã tính |
| Phương thức không trả kết quả | Kiểu trả về `void` |

Java truyền đối số theo giá trị. Với tham chiếu, giá trị được truyền là bản sao tham chiếu; việc gán lại tham số trong phương thức không tự đổi biến tham chiếu của bên gọi. Nhưng nếu cả hai cùng tham chiếu một đối tượng có thể thay đổi, việc sửa đối tượng đó có thể được quan sát ở bên gọi.

Hiểu điểm này giúp tránh hiểu sai biến phần tử trong vòng lặp và dữ liệu dùng chung.

### 5.3. Overload khác override

Overload là nhiều phương thức cùng tên với danh sách tham số khác nhau. Override là lớp cung cấp cách thực hiện cho phương thức được thừa kế hoặc khai báo trong giao diện theo quy tắc tương ứng.

Phân biệt này cần thiết khi học boxing, varargs và `@Override`. Chưa cần giải hết mọi trường hợp lựa chọn overload khó trước khi bắt đầu; chỉ cần nhận ra hai cơ chế đang khác nhau.

## 6. Lớp, đối tượng và giao diện

Một lớp nhỏ có thể chứa:

- Trường dữ liệu.
- Hàm dựng để tạo trạng thái hợp lệ.
- Phương thức cho hành vi.
- Phạm vi truy cập như `private`, `public`.
- Thành viên `static` thuộc lớp và thành viên gắn với từng đối tượng.

Trong ví dụ, `Learner` giữ tên và điểm. Hàm dựng từ chối tên thiếu hoặc điểm ngoài 0..100. Bên ngoài không trực tiếp đổi các trường `private final`.

Từ đó, người học cần giải thích được:

1. `new Learner(...)` tạo đối tượng.
2. Hàm dựng thiết lập và kiểm tra trạng thái đầu vào.
3. Phương thức đọc dữ liệu qua một giao diện có chủ đích.
4. Giao diện `Named` mô tả khả năng cung cấp tên; lớp `Learner` thực hiện khả năng đó.
5. Một tham chiếu kiểu giao diện có thể trỏ tới đối tượng của lớp thực hiện giao diện.

Không cần thiết kế một hệ phân cấp lớp phức tạp để chứng minh đã hiểu OOP. Một ví dụ đủ nhỏ giúp thấy đúng quan hệ kiểu và việc gọi phương thức.

Nền tảng này được dùng lại khi học lớp tổng quát, giới hạn kiểu, enum có trường/phương thức và các API nhận giao diện tác vụ. Xem quy tắc lớp và phương thức tại [JLS, chương Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html).

## 7. So sánh đối tượng: hiểu equals trước khi học sâu wrapper và collection

Với tham chiếu:

- `==` kiểm tra hai tham chiếu có trỏ cùng đối tượng hay cùng là `null` không.
- `equals` được dùng để so giá trị theo hợp đồng của lớp.

Hai đối tượng `String` có nội dung “An” có thể bằng nhau qua `equals` dù không cần cùng danh tính đối tượng.

Không suy ra rằng mọi lớp tự viết đều có `equals` theo mọi trường. Một lớp tự viết kế thừa hành vi mặc định từ `Object` nếu chưa định nghĩa quy tắc riêng. Khi học sâu collection, cần bổ sung quan hệ giữa `equals` và `hashCode` cho các cấu trúc dùng băm.

Ở bước chuẩn bị, tiêu chí tối thiểu là chọn đúng phép so cho `String`, hiểu tham chiếu và không đoán rằng hai số được đóng gói sẽ luôn có cùng đối tượng. Những quy tắc riêng của wrapper sẽ được học ở phần boxing/unboxing.

## 8. Ngoại lệ và cách đọc lỗi

Người học nên phân biệt:

| Loại vấn đề | Ví dụ | Thời điểm phát hiện |
| --- | --- | --- |
| Sai cú pháp hoặc kiểu | Gọi phương thức không tồn tại trên kiểu biến | Khi biên dịch |
| Đầu vào bị từ chối | Điểm 101 trong ví dụ | Khi chạy |
| Truy cập không hợp lệ | Chỉ số nằm ngoài mảng | Khi chạy |
| Gọi phương thức trên `null` | Tham chiếu thiếu nhưng vẫn dùng | Khi chạy |

Cần đọc được tên ngoại lệ, thông điệp và vị trí gây lỗi trong stack trace. Biết `try/catch`, `throw`, `throws` ở mức cơ bản; biết có ngoại lệ được kiểm tra khi biên dịch và ngoại lệ không bắt buộc khai báo/bắt.

Bắt ngoại lệ không có nghĩa lỗi đã được giải quyết. Không bắt mọi lỗi rồi trả giá trị thành công giả. Trong ví dụ, ngoại lệ chỉ được bắt ở các ca cố ý kiểm tra đầu vào sai; các lỗi không được dự kiến vẫn khiến chương trình thất bại.

Nền này giúp học generics như một cách đẩy một số lỗi kiểu sang bước biên dịch, và giúp hiểu tác vụ đồng thời có thể hoàn thành với kết quả hoặc thất bại bằng ngoại lệ. Chưa cần học sẵn mọi API quản lý tác vụ để bắt đầu nhóm tính năng ngôn ngữ.

## 9. Package, import và đọc tài liệu API

Cần hiểu:

- Package tổ chức tên kiểu.
- `import` giúp viết tên ngắn trong tệp nguồn, không phải thao tác tự tạo đối tượng.
- Các kiểu phổ biến trong `java.lang` như `String`, `System` không cần một dòng import riêng.
- `static` member khác phương thức của một đối tượng.
- Chữ ký API cho biết tham số, kết quả và các điều kiện cần đọc thêm.

Điều này chuẩn bị cho static import: muốn hiểu nó, trước hết phải hiểu thành viên static và phạm vi tên. Không cần dùng static import ở mọi nơi chỉ vì nó làm mã ngắn.

Khi tài liệu hiện đại của `List` xuất hiện ký hiệu `List<E>`, người học chưa cần phân tích hết quy tắc `E` ngay. Trước tiên nhận biết đây là giao diện danh sách có phần tử, rồi học generics để hiểu sự ràng buộc kiểu của phần tử.

## 10. Collection và xử lý đồng thời: bổ sung theo nhánh cần học

### 10.1. Collection ở mức khái niệm

Trước phần generics/duyệt collection, nên biết một danh sách dùng để chứa nhiều phần tử, có thể thêm/đọc/duyệt theo hợp đồng của nó, và giao diện khác lớp thực hiện.

Không cần luyện bằng collection không khai báo kiểu phần tử. Khi bắt đầu dùng collection trong mã mới, học luôn cú pháp có kiểu cùng bài generics; không tạo thói quen viết mã bỏ qua kiểm tra kiểu rồi mới sửa lại.

Cần hiểu danh sách và mảng không có cùng hợp đồng: mảng có độ dài cố định, còn khả năng thay đổi kích thước của danh sách phụ thuộc cách thực hiện cụ thể. Không suy từ tên `List` rằng mọi danh sách đều cho phép thêm phần tử. Hợp đồng hiện tại có ở [List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

### 10.2. Kiến thức bổ sung trước các API đồng thời

Nếu đi vào nhóm tiện ích đồng thời, cần hiểu trước:

- Tác vụ là việc cần làm; luồng là một ngữ cảnh thực thi tác vụ.
- Các tác vụ có thể cùng truy cập dữ liệu có thể thay đổi.
- Thứ tự thực thi không phải lúc nào cũng cố định.
- Chờ hoàn thành, hủy và xử lý lỗi là một phần của vòng đời tác vụ.
- An toàn đồng thời không tự xuất hiện chỉ vì lớp nằm trong một chương trình Java.

Chỉ cần hiểu vấn đề trước khi học cách giải bằng API cụ thể. Không cần tự viết thread pool hoặc tự dựng mọi cơ chế khóa như một điều kiện bắt buộc.

Các khái niệm `Executor`, `ExecutorService`, `Callable` vẫn có mặt trong thư viện hiện đại; lựa chọn API cụ thể cần theo yêu cầu hiện tại, không sao chép mọi mẫu lịch sử. Xem tổng quan [java.util.concurrent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html).

## 11. Chương trình tự kiểm tra nền tảng trên Java 17+

Lưu mã sau thành `Java5Readiness.java`. Đây là bài kiểm tra khả năng đọc nền tảng, không phải bài triển khai các tính năng Java 5.

Ví dụ dùng lớp, giao diện, mảng, vòng lặp theo chỉ số và ngoại lệ. `String.isBlank()` là một tiện ích Java hiện đại để kiểm tra tên, không phải nội dung được gán cho Java 5. Chương trình cố ý chạy trên JDK hiện đại.

```java
interface Named {
    String name();
}

final class Learner implements Named {
    private final String name;
    private final int score;

    Learner(String name, int score) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score must be 0..100");
        }
        this.name = name;
        this.score = score;
    }

    public String name() {
        return name;
    }

    int score() {
        return score;
    }
}

public class Java5Readiness {
    private static int checks;

    private static int sum(int[] values) {
        int total = 0;
        for (int i = 0; i < values.length; i++) {
            total += values[i];
        }
        return total;
    }

    private static int countPassed(Learner[] learners, int threshold) {
        int count = 0;
        for (int i = 0; i < learners.length; i++) {
            if (learners[i].score() >= threshold) {
                count++;
            }
        }
        return count;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        checks++;
    }

    public static void main(String[] args) {
        int[] scores = {80, 55, 90};
        Learner[] learners = {
            new Learner("An", scores[0]),
            new Learner("Binh", scores[1]),
            new Learner("Chi", scores[2])
        };

        Named first = learners[0];
        Named sameObject = learners[0];
        check(first.name().equals("An"), "Interface method result");
        check(first == sameObject, "Two references to one object");
        check(new String("An").equals(first.name()), "Text value equality");
        check(sum(scores) == 225, "Sum of scores");
        check(countPassed(learners, 60) == 2, "Pass count");
        check(sum(new int[0]) == 0, "Empty array");
        check(countPassed(new Learner[0], 60) == 0, "No learners");

        boolean rejected = false;
        try {
            new Learner("Invalid", 101);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "Invalid score must be rejected");

        boolean missingNameRejected = false;
        try {
            new Learner(null, 50);
        } catch (IllegalArgumentException expected) {
            missingNameRejected = true;
        }
        check(missingNameRejected, "Missing name must be rejected");

        System.out.println("first=" + first.name());
        System.out.println("total=" + sum(scores));
        System.out.println("passed=" + countPassed(learners, 60));
        System.out.println("invalidScoreRejected=" + rejected);
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 Java5Readiness.java
java Java5Readiness
```

Stdout:

```text
first=An
total=225
passed=2
invalidScoreRejected=true
PASS checks=9
```

Trong một tệp này, `Java5Readiness` là lớp `public`; tên tệp phải khớp. `Named` và `Learner` là các kiểu bổ trợ cùng tệp để ví dụ độc lập và dễ chạy.

Hàm `check` chủ động ném `AssertionError` khi điều kiện sai, nên không cần bật `-ea`. Chín lần kiểm tra gồm gọi qua giao diện, hai tham chiếu cùng đối tượng, so nội dung chuỗi, tổng/đếm phần tử, mảng rỗng và hai đầu vào bị từ chối.

Không chỉ chạy rồi thấy PASS. Hãy giải thích được mỗi dòng đầu ra và từng đường đi dẫn đến nó.

## 12. Đọc ví dụ để biết phần nào cần ôn

| Câu hỏi tự kiểm tra | Điều cần giải thích được |
| --- | --- |
| Vì sao tổng là 225? | Vòng lặp đi qua ba điểm và cộng tích lũy |
| Vì sao có 2 người đạt? | Điều kiện điểm >= 60 chọn 80 và 90 |
| Vì sao `Named first` gọi được `name()`? | Phương thức thuộc hợp đồng giao diện và được lớp thực hiện |
| Vì sao không gọi `score()` trực tiếp qua biến `Named`? | Kiểu tĩnh không khai báo phương thức đó |
| `first == sameObject` đang kiểm tra gì? | Hai tham chiếu cùng đối tượng |
| Vì sao dùng `equals` với chuỗi mới tạo? | So nội dung văn bản, không yêu cầu cùng danh tính |
| Mảng rỗng có phải `null` không? | Không; nó vẫn là đối tượng mảng có độ dài 0 |
| Vì sao tên `null` không gây lỗi tại `isBlank()`? | Điều kiện `||` đánh giá ngắn mạch |
| Điểm 101 thất bại ở biên dịch hay lúc chạy? | Là `int` hợp lệ về kiểu, bị quy tắc hàm dựng từ chối lúc chạy |
| `final` ở biến trường đảm bảo gì? | Trường không được gán lại sau khi thiết lập theo quy tắc; không tự làm mọi đối tượng tham chiếu bất biến sâu |

Nếu chưa giải thích được một dòng, ôn đúng nền tương ứng rồi chạy lại sau khi tự thay đổi ví dụ. Không cần trì hoãn toàn bộ việc học chỉ vì chưa biết một API nâng cao chưa liên quan.

## 13. Những thứ chưa cần biến thành rào cản

Trước khi bắt đầu các tính năng Java 5, chưa cần:

- Viết generic class hay giải thích wildcard thành thạo: đó là nội dung sẽ học.
- Thuộc cơ chế xóa kiểu hoặc mọi giới hạn của generic array.
- Tự viết bộ xử lý annotation hoặc hiểu toàn bộ reflection.
- Hiểu hết Java Memory Model trước những bài cú pháp không liên quan đồng thời.
- Biết Spring, cơ sở dữ liệu hoặc một framework kiểm thử để chạy ví dụ ngôn ngữ nhỏ.
- Dùng lambda, stream, record hoặc tính năng cú pháp mới để thay mọi đoạn mã nền tảng.

Những kiến thức vẫn có ích ở đúng giai đoạn sẽ được bổ sung khi cần. Ví dụ annotations cần hiểu vị trí khai báo và ý nghĩa metadata; cách đọc metadata lúc chạy chỉ cần khi bài toán thực sự dùng nó.

Mục đích là có đường học vừa đủ: nền tảng chung trước, cơ chế của tính năng sau, rồi ví dụ và thực hành tương ứng.

## 14. Bài tập chuẩn bị ngắn

1. **Đổi ngưỡng đạt thành 90.** Kết quả phải còn 1 người đạt. Giải thích vì sao điều kiện `>=` chấp nhận đúng 90.

2. **Thêm người có điểm 60.** Cập nhật mảng đầu vào và dự đoán tổng, số người đạt trước khi chạy. Phân biệt dữ liệu mới với việc thay đổi thuật toán.

3. **Tạo mảng có một phần tử `null`.** Dự đoán điều gì xảy ra khi vòng lặp gọi `score()`. Sau đó xác định hợp đồng hàm nên từ chối hay xử lý phần tử thiếu; không bắt lỗi rồi tự tính là đạt.

4. **Thêm một lớp khác thực hiện `Named`.** Gọi `name()` qua biến giao diện và giải thích vì sao hợp đồng không gắn riêng với `Learner`.

5. **Viết một phương thức trả điểm cao nhất.** Nêu trước cách xử lý mảng rỗng. Không tự lấy 0 làm câu trả lời nếu chưa xác định quy tắc dữ liệu.

6. **Phân loại một lỗi tự tạo.** Thử gọi phương thức không có trên kiểu biến, rồi thử tạo điểm 101. Một lỗi do trình biên dịch báo; lỗi kia được quy tắc lúc chạy phát hiện.

Khi có thể đọc và chỉnh ví dụ nền tảng mà vẫn giải thích đúng kiểu, đối tượng và luồng chạy, người học đã có cơ sở để tiếp cận các tính năng Java 5 còn được dùng trong mã hiện đại.
