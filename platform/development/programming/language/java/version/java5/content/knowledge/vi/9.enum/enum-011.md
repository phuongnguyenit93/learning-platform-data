# Sử dụng enum với câu lệnh switch

## 1. Enum làm tập lựa chọn có tên và có kiểu

Enum mô tả một tập các hằng thuộc cùng một kiểu. Khi hành vi phụ thuộc vào giá trị enum, `switch` giúp trình bày các nhánh theo tên trạng thái thay vì dựa vào chuỗi hoặc mã số:

```java
enum JobStatus {
    QUEUED, RUNNING, SUCCEEDED, FAILED
}
```

Với một biến `JobStatus status`, câu lệnh `switch (status)` chọn nhánh ứng với hằng enum đang được giữ. Tên `QUEUED` hay `FAILED` giúp người đọc thấy ý nghĩa nghiệp vụ mà không cần nhớ “mã 0 nghĩa là gì”.

Bài này tập trung vào **câu lệnh switch (switch statement)**: thực hiện một công việc theo nhánh, rồi tiếp tục luồng chương trình. Các ví dụ chính chạy với Java 17 trở lên. Phần riêng về `case null` được ghi rõ yêu cầu Java 21 trở lên.

## 2. Nhãn mũi tên: một nhánh không tự chạy sang nhánh kế tiếp

Đây là phương thức minh họa, đặt trong một lớp có thể dùng kiểu `JobStatus`:

```java
static void handle(JobStatus status) {
    java.util.Objects.requireNonNull(status, "status");
    switch (status) {
        case QUEUED -> System.out.println("wait");
        case RUNNING -> System.out.println("work");
        case SUCCEEDED, FAILED -> System.out.println("finished: " + status);
    }
    System.out.println("after switch");
}
```

Trong ví dụ, selector đã có kiểu `JobStatus`, nên các nhãn viết ngắn gọn bằng tên hằng enum. Không thay nhãn bằng chuỗi như `case "QUEUED"` khi selector vẫn là `JobStatus`: đó là hai kiểu dữ liệu khác nhau. `case SUCCEEDED, FAILED` gom hai hằng có chung cách xử lý.

Với nhãn `->`, khi nhánh khớp thực hiện xong bình thường, nó không tự rơi xuống chạy mã của nhánh tiếp theo. Không cần thêm `break` chỉ để ngăn fall-through.

Dạng này vẫn là **switch statement**. Dấu mũi tên không tự biến toàn bộ cấu trúc thành một switch expression. Ở đây `switch` không được dùng làm giá trị để gán hay trả về; nó thực hiện các lời gọi in.

Nếu nhánh cần nhiều câu lệnh hoặc biến cục bộ, dùng block:

```java
switch (status) {
    case QUEUED -> System.out.println("wait");
    case RUNNING -> {
        String message = "processing " + status;
        System.out.println(message);
        System.out.println("keep monitoring");
    }
    case SUCCEEDED, FAILED -> System.out.println("finished");
}
```

Đoạn này là các câu lệnh trong một phương thức có biến `status` khác null. Block làm rõ phạm vi của biến `message` và nhóm các thao tác thuộc cùng một nhánh.

## 3. Dạng dấu hai chấm: cần kiểm soát fall-through

Cú pháp `case ...:` vẫn được hỗ trợ trong Java hiện hành. Nó có quy tắc luồng khác với nhãn mũi tên:

```java
static void handleWithColon(JobStatus status) {
    java.util.Objects.requireNonNull(status, "status");
    switch (status) {
        case QUEUED:
            System.out.println("wait");
            break;
        case RUNNING:
            System.out.println("work");
            break;
        case SUCCEEDED:
        case FAILED:
            System.out.println("finished: " + status);
            break;
    }
}
```

Sau khi đi vào một nhánh dấu hai chấm, các câu lệnh phía sau có thể tiếp tục được chạy theo thứ tự cho đến khi gặp một lệnh kết thúc luồng phù hợp, chẳng hạn `break`, `return` hoặc `throw`. Chúng không tự dừng chỉ vì đã tới một nhãn `case` khác.

Nếu bỏ `break` sau phần in `wait`, trạng thái `QUEUED` còn có thể chạy phần in `work` ở nhánh kế tiếp. Đây là **fall-through**, thường là lỗi khi mỗi trạng thái cần một cách xử lý độc lập.

Hai nhãn trống `case SUCCEEDED:` và `case FAILED:` trong ví dụ cố ý dùng chung một nhóm câu lệnh. Đây là cách gom nhánh hợp lệ; nhãn mũi tên tương ứng có thể viết `case SUCCEEDED, FAILED -> System.out.println("finished");`.

Không trộn các nhãn `case ...:` và các quy tắc `case ... ->` trong cùng một switch block. Chọn một dạng và áp dụng nhất quán cho cấu trúc đó.

## 4. break kết thúc switch, không kết thúc phương thức

Trong `handle`, câu lệnh sau switch vẫn được chạy khi nhánh kết thúc bình thường. Với dạng dấu hai chấm, `break` không nhãn ở trong switch kết thúc switch gần nhất, rồi chương trình tiếp tục ngay sau nó.

Phân biệt:

| Chuyển luồng trong nhánh | Tác dụng |
| --- | --- |
| Nhánh `->` kết thúc bình thường | Ra khỏi switch statement, chạy phần sau switch |
| `break;` trong dạng `case ...:` | Kết thúc switch gần nhất phù hợp |
| `return;` trong phương thức `void` | Kết thúc toàn bộ phương thức |
| `throw ...` | Ném ngoại lệ, đi theo cơ chế xử lý ngoại lệ |

Nếu switch nằm trong một vòng lặp, `break` của switch không tự dừng vòng lặp bên ngoài. Cần đọc đúng cấu trúc bao quanh thay vì coi `break` là “thoát mọi tầng”.

Ngược lại, `return` có thể bỏ qua các câu lệnh sau switch trong cùng phương thức. Chỉ dùng nó khi đúng ý định, chẳng hạn một phương thức đã xử lý xong toàn bộ yêu cầu.

## 5. Chương trình chạy đầy đủ với Java 17 trở lên

Lưu thành **`EnumSwitchDemo.java`**:

```java
import java.util.Objects;

public class EnumSwitchDemo {
    enum JobStatus {
        QUEUED, RUNNING, SUCCEEDED, FAILED
    }

    static void handle(JobStatus status) {
        Objects.requireNonNull(status, "status");
        switch (status) {
            case QUEUED -> System.out.println("queued: wait");
            case RUNNING -> {
                System.out.println("running: work");
            }
            case SUCCEEDED, FAILED -> System.out.println("terminal: " + status);
        }
        System.out.println("after=" + status);
    }

    public static void main(String[] args) {
        for (JobStatus status : JobStatus.values()) {
            handle(status);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all EnumSwitchDemo.java
java EnumSwitchDemo
```

Stdout chính xác:

```text
queued: wait
after=QUEUED
running: work
after=RUNNING
terminal: SUCCEEDED
after=SUCCEEDED
terminal: FAILED
after=FAILED
```

`values()` duyệt các hằng theo thứ tự khai báo trong enum. Mỗi trạng thái khớp đúng nhánh của nó, và dòng `after=...` vẫn được in sau khi nhánh kết thúc. Ví dụ gom hai trạng thái cuối vì cùng cần thông báo công việc đã kết thúc.

`Objects.requireNonNull` là lựa chọn hợp đồng của phương thức: nó từ chối thiếu trạng thái ngay tại đầu vào. Nó không biến `null` thành một hằng enum mới hoặc thành nhánh `default`.

## 6. default không phải cách bắt null

Với một switch enum không có nhãn xử lý null, selector `null` gây `NullPointerException`; `default` không tự nhận nó như một giá trị enum lạ.

```java
JobStatus status = null;
// Nếu không kiểm tra null trước và không có case null phù hợp:
// switch (status) sẽ ném NullPointerException, không đi vào default.
```

Một biến enum có thể là một trong các hằng hợp lệ hoặc là tham chiếu null. Không có một giá trị enum tùy ý khác nằm ngoài các hằng chỉ vì đầu vào là một số nguyên lạ.

Dữ liệu bên ngoài cần được chuyển và kiểm tra trước khi đi vào tầng xử lý enum. Ví dụ, chuyển chuỗi bằng `JobStatus.valueOf(text)` có quy tắc riêng và có thể ném `IllegalArgumentException` khi tên không khớp; nhánh default của một switch diễn ra sau đó không xử lý lỗi parse đã xảy ra trước lời gọi.

Nếu nghiệp vụ có một trạng thái “chưa biết”, hãy mô hình hóa và xử lý nó theo hợp đồng rõ ràng. Không tự đồng nhất trạng thái đó với null hoặc một lỗi nhập liệu chỉ vì tất cả đều cần một đường dự phòng trong giao diện.

## 7. Java 21 trở lên: xử lý null bằng case null

Java hiện hành hỗ trợ nhãn `case null`. Ví dụ sau cần **Java 21 trở lên**, không biên dịch bằng `--release 17`.

Lưu thành **`EnumNullSwitchDemo.java`**:

```java
public class EnumNullSwitchDemo {
    enum JobStatus {
        QUEUED, RUNNING, SUCCEEDED, FAILED
    }

    static void show(JobStatus status) {
        switch (status) {
            case null -> System.out.println("missing status");
            case QUEUED, RUNNING -> System.out.println("active");
            case SUCCEEDED, FAILED -> System.out.println("terminal");
        }
    }

    public static void main(String[] args) {
        show(null);
        show(JobStatus.RUNNING);
        show(JobStatus.FAILED);
    }
}
```

Biên dịch và chạy với JDK phù hợp:

```shell
javac --release 21 -Xlint:all EnumNullSwitchDemo.java
java EnumNullSwitchDemo
```

Stdout chính xác:

```text
missing status
active
terminal
```

Ví dụ xử lý đủ null và mọi hằng enum. Sự có mặt của nhãn null làm cấu trúc thuộc các quy tắc switch được mở rộng của Java hiện hành, trong đó yêu cầu tính đầy đủ cần được giữ đúng. Không lấy một ví dụ switch enum statement chỉ dùng các hằng rồi suy ra rằng mọi kiểu switch mới đều được phép bỏ các trường hợp còn lại.

Chọn từ chối null ở ranh giới như chương trình Java 17 hay hỗ trợ null bằng nhánh riêng như chương trình này là một quyết định hợp đồng, không chỉ là đổi cú pháp cho qua bước biên dịch.

## 8. Tính đầy đủ và việc enum thay đổi theo thời gian

Với switch statement enum thông thường chỉ dùng các nhãn hằng như các ví dụ Java 17, Java có thể cho phép một cấu trúc chưa liệt kê hết hằng. Nếu không có nhánh khớp và không có `default`, không nhánh nào được thực hiện; chương trình tiếp tục sau switch.

Điều này khác với yêu cầu tính đầy đủ của switch expression và các switch statement được mở rộng trong những ngữ cảnh tương ứng. Không nói chung rằng “switch enum luôn được compiler bắt thiếu case” chỉ vì kiểu enum có một tập hằng hữu hạn.

Khi thêm một hằng enum mới, cần xem lại các nơi xử lý theo trạng thái. Một phương thức switch statement cũ có thể vẫn biên dịch nhưng không làm công việc dự định cho trạng thái mới.

Việc có thêm `default` hay không phải theo ý nghĩa API:

- Nếu có một xử lý chung đúng cho mọi giá trị chưa liệt kê, `default` có thể thể hiện lựa chọn đó.
- Nếu bỏ qua một trạng thái là lỗi thiết kế, cần một cơ chế phát hiện rõ như nhánh ném ngoại lệ, kiểm thử bao phủ các hằng hoặc một cấu trúc yêu cầu tính đầy đủ phù hợp với kết quả cần tạo.
- Không thêm `default` rỗng chỉ để che việc chưa quyết định cách xử lý trạng thái mới.

Trong bài, chương trình chính liệt kê toàn bộ bốn trạng thái và chạy qua `values()` để quan sát từng đường xử lý. Việc chạy như vậy là bằng chứng cho tập enum hiện tại, không thay thế việc xem lại hợp đồng khi enum được mở rộng.

## 9. Không switch theo ordinal để mã hóa nghiệp vụ

Nên dùng trực tiếp hằng enum:

```java
switch (status) {
    case QUEUED -> System.out.println("wait");
    case RUNNING -> System.out.println("work");
    case SUCCEEDED, FAILED -> System.out.println("done");
}
```

Không đổi thành `switch (status.ordinal())` rồi hardcode `case 0`, `case 1` để đại diện nghiệp vụ. Thứ tự khai báo có thể thay đổi hoặc có thêm hằng chèn vào, làm các con số mang ý nghĩa khác.

Tương tự, `switch (status.name())` đẩy lựa chọn trở lại kiểu `String` và không còn cùng các bảo đảm về nhãn enum. Dùng chuỗi hoặc mã ngoài hệ thống khi cần giao tiếp dữ liệu là vấn đề khác; hãy chuyển đổi tại ranh giới và dùng enum có kiểu ở tầng xử lý phù hợp.

`switch` dựa vào chính giá trị hằng enum, không dựa vào văn bản hiển thị mà một hằng có thể cung cấp qua `toString()` tùy biến. Đừng trộn tên hằng, nhãn người dùng và mã lưu trữ thành một khái niệm duy nhất.

## 10. Chọn switch hay đưa hành vi vào enum?

Switch phù hợp khi một thao tác bên ngoài enum có cách xử lý khác nhau theo một tập trạng thái rõ ràng. Ví dụ, một bộ phận hiển thị chọn thông báo còn một bộ phận khác chọn mức cảnh báo.

Nếu nhiều nơi lặp lại cùng một switch chỉ để lấy cùng một thuộc tính cố định của từng hằng, có thể cân nhắc trường dữ liệu hoặc phương thức của enum để tránh lặp quy tắc. Quyết định này cần dựa vào trách nhiệm của kiểu, không phải chỉ để xóa mọi switch khỏi mã.

Với một state machine thực sự, việc một trạng thái xuất hiện trong case không chứng minh chuyển trạng thái được phép. Nếu cần quy tắc như “chỉ RUNNING mới được chuyển sang SUCCEEDED”, phải mô tả và kiểm tra rõ quan hệ chuyển trạng thái; một switch in thông báo không tự tạo ra bảo đảm ấy.

## 11. Lỗi thường gặp

| Nhầm lẫn | Cách đọc hoặc sửa |
| --- | --- |
| Nghĩ `->` chỉ dùng được cho switch expression | Dùng được cả trong statement; xác định switch có tạo giá trị ở nơi dùng hay không |
| Quên break với nhánh dấu hai chấm | Kiểm tra fall-through; dùng mũi tên cho các nhánh độc lập nếu phù hợp |
| Dùng default để xử lý selector null | Kiểm tra/từ chối null trước, hoặc dùng case null ở mức Java hỗ trợ |
| Cho rằng bỏ một case luôn là lỗi biên dịch | Xét đúng loại switch và yêu cầu tính đầy đủ |
| Dùng ordinal như mã nghiệp vụ ổn định | Dùng nhãn enum trực tiếp; mã ngoài hệ thống cần hợp đồng riêng |
| Thêm hằng mới nhưng giữ nguyên hành vi cũ theo thói quen | Audit các nơi switch và kiểm thử những nhánh cần có |

## 12. Tự thực hành

1. Chạy chương trình Java 17 với đầy đủ `values()`, rồi đổi cách gom hai trạng thái cuối thành hai nhánh độc lập. Xác nhận mỗi trạng thái chỉ thực hiện đúng phần đã chọn.
2. Viết một phương thức dấu hai chấm có `break` đầy đủ, sau đó cố ý bỏ một `break` để quan sát fall-through. Khôi phục trước khi dùng làm ví dụ đúng.
3. Thêm `CANCELLED` vào enum trong một bản thí nghiệm. Kiểm tra phương thức nào vẫn biên dịch và nhánh nào đang thiếu hành vi.
4. Gọi chương trình chính với null và so sánh hợp đồng từ chối với chương trình `case null` trên Java 21.
5. Thêm câu lệnh sau switch, rồi thử `return` ở một nhánh. Phân biệt việc kết thúc switch với việc kết thúc toàn bộ phương thức.

Để dùng switch với enum chính xác, cần nhìn cả tập hằng, dạng nhãn, cách kết thúc nhánh và hợp đồng đối với null. Những yếu tố đó quyết định luồng thật sự của chương trình, không chỉ là cách viết danh sách case.

## Tài liệu đối chiếu

- [JLS §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11): nhãn, tính đầy đủ và hành vi thực thi switch statement.
- [Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): nhãn mũi tên dùng được trong statement và cách nhóm nhãn.
- [JLS §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9): hằng enum và các thành viên được cung cấp cho kiểu enum.
