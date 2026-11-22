# Nhánh mở rộng được phép và giới hạn của anonymous class, lambda

## Mục tiêu

Trong Java, `sealed` cho phép một class hoặc interface kiểm soát những kiểu nào được kế thừa hoặc triển khai trực tiếp. Anonymous class và lambda đều giúp tạo hành vi tại chỗ, nhưng chúng không thể bỏ qua các quy tắc của một hierarchy `sealed`.

Sau bài này, bạn sẽ phân biệt được:
- kiểu con trực tiếp được khai báo trong `permits` với kiểu con gián tiếp;
- giới hạn của anonymous class khi mở rộng một kiểu `sealed`;
- vì sao lambda không thể triển khai trực tiếp một sealed interface;
- cách mở một nhánh mở rộng có chủ đích bằng `non-sealed`.

## 1. Trực tiếp và gián tiếp quyết định khả năng mở rộng

~~~java
sealed interface Payment permits CardPayment, ExternalPayment {}

final class CardPayment implements Payment {}

non-sealed class ExternalPayment implements Payment {}
~~~

`Payment` chỉ cho phép hai kiểu triển khai trực tiếp được đặt tên. `CardPayment` đóng nhánh, còn `ExternalPayment` mở nhánh. Một class nằm dưới `ExternalPayment` là hậu duệ **gián tiếp** của `Payment`, không cần được liệt kê lại trong `permits`. Anonymous class có thể mở rộng `ExternalPayment`; ngược lại, nó không thể tự tạo một kiểu con trực tiếp mới cho `Payment`. Lambda cũng tuân thủ ranh giới của kiểu mục tiêu, nhưng có quy tắc riêng về functional interface được giải thích phía dưới.

## 2. Giới hạn của anonymous class

Anonymous class là một lớp không có tên được khai báo ngay tại biểu thức tạo đối tượng. Ví dụ thông thường:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

Cách viết này hợp lệ vì `Runnable` là interface không bị sealed. Tuy nhiên, anonymous class không thể trở thành kiểu con trực tiếp của một class hoặc interface `sealed`. Kiểu con trực tiếp phải là kiểu có tên, được phép trong hierarchy; anonymous class không thể được nêu như một kiểu cụ thể trong mệnh đề `permits`.

Ví dụ sau **không hợp lệ**:

~~~java
sealed interface Command permits StartCommand {
}

final class StartCommand implements Command {
}

class Main {
    public static void main(String[] args) {
        Command command = new Command() {
            // Anonymous class đang cố triển khai Command trực tiếp.
        };
    }
}
~~~

Trình biên dịch từ chối anonymous class vì kiểu mới tạo không phải là một kiểu con trực tiếp được cho phép. Thêm một đối tượng vào danh sách `permits` cũng không giải quyết được vấn đề: `permits` liệt kê kiểu, không liệt kê đối tượng, và anonymous class không có tên nguồn để khai báo ở đó.

Anonymous class vẫn có thể mở rộng hoặc triển khai một kiểu **không bị sealed**, kể cả khi kiểu đó là một nhánh mở rộng của sealed hierarchy. Đây là cách mở rộng có chủ đích thay vì phá vỡ ranh giới đã định nghĩa.

## 3. Vì sao lambda có giới hạn khác?

Lambda expression không phải là cú pháp tạo một lớp con tùy ý. Lambda cung cấp phần triển khai cho một **functional interface** — interface có một phương thức trừu tượng phù hợp làm hợp đồng chức năng.

Ví dụ:

~~~java
@FunctionalInterface
interface Handler {
    void handle();
}

class Main {
    public static void main(String[] args) {
        Handler handler = () -> System.out.println("handled");
        handler.handle();
    }
}
~~~

Lambda ở đây triển khai hợp đồng `handle()` của `Handler`. Lambda không kế thừa một class, cũng không cung cấp một tên kiểu con để ghi vào `permits`.

Một sealed interface không thể làm functional interface mục tiêu cho lambda: định nghĩa functional interface của Java loại trừ interface `sealed`. Do đó, không thể dùng lambda để tạo một kiểu triển khai trực tiếp cho sealed interface. Nếu cố gán lambda cho sealed interface, chương trình sẽ không biên dịch.

Điều này không có nghĩa là lambda bị cấm hoàn toàn trong sealed hierarchy. Lambda có thể nhắm tới một functional interface `non-sealed` nằm trong một nhánh được cho phép. Khi đó, kiểu trực tiếp nằm dưới sealed interface là interface `non-sealed` có tên; lambda chỉ cung cấp hành vi cho interface mở rộng ấy.

## 4. Mở một nhánh hợp lệ cho anonymous class và lambda

Ví dụ hoàn chỉnh sau minh họa cách thiết kế đó. Lưu toàn bộ mã vào `Main.java`:

~~~java
sealed interface Job permits BuiltInJob, ExtensibleJob {
}

record BuiltInJob(String name) implements Job {
}

@FunctionalInterface
non-sealed interface ExtensibleJob extends Job {
    void execute();
}

public class Main {
    public static void main(String[] args) {
        ExtensibleJob lambdaJob =
                () -> System.out.println("lambda job");

        ExtensibleJob anonymousJob = new ExtensibleJob() {
            @Override
            public void execute() {
                System.out.println("anonymous job");
            }
        };

        lambdaJob.execute();
        anonymousJob.execute();

        Job builtIn = new BuiltInJob("report");
        System.out.println(builtIn instanceof BuiltInJob);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Đầu ra chuẩn chính xác:

~~~text
lambda job
anonymous job
true
~~~

Phân tích ví dụ:

1. `Job` là sealed interface. Hai kiểu con trực tiếp được phép là `BuiltInJob` và `ExtensibleJob`.
2. `BuiltInJob` là record nên tự động là kiểu `final`; nó không mở rộng hierarchy thêm nữa.
3. `ExtensibleJob` được khai báo `non-sealed`, vì vậy các kiểu khác có thể triển khai interface này. Nó có đúng một phương thức trừu tượng là `execute()`, nên có thể dùng làm mục tiêu cho lambda.
4. `lambdaJob` cung cấp thân hàm bằng lambda. `anonymousJob` dùng anonymous class để triển khai cùng interface mở rộng. Cả hai đối tượng đều là `Job` theo quan hệ kiểu gián tiếp thông qua `ExtensibleJob`.
5. Biểu thức `builtIn instanceof BuiltInJob` in ra `true`, vì đối tượng được tạo là một `BuiltInJob`.

Thiết kế này giữ được một ranh giới rõ: sealed interface chỉ cho phép hai nhánh trực tiếp đã định danh, nhưng một nhánh `non-sealed` có thể cho phép các cách triển khai linh hoạt như lambda và anonymous class.

## 5. So sánh nhanh

| Trường hợp | Hợp lệ? | Lý do |
|---|---|---|
| Anonymous class trực tiếp triển khai sealed interface | Không | Không thể khai báo anonymous class làm kiểu con trực tiếp được phép |
| Anonymous class triển khai interface `non-sealed` trong hierarchy | Có | Kiểu trực tiếp của anonymous class là nhánh mở đã được cho phép |
| Lambda nhắm tới sealed interface | Không | Sealed interface không thể là functional interface mục tiêu |
| Lambda nhắm tới functional interface `non-sealed` trong hierarchy | Có | Functional interface mở có thể nhận phần triển khai từ lambda |
| Kiểu `final` được khai báo trong `permits` | Có | Kiểu con trực tiếp có tên và đóng nhánh kế thừa |
| Kiểu `non-sealed` được khai báo trong `permits` | Có | Kiểu con trực tiếp có tên và mở các nhánh con tiếp theo |

## 6. Lỗi thường gặp và cách xử lý

**Cố đưa anonymous class vào `permits`.** Mệnh đề này khai báo các kiểu con trực tiếp bằng tên kiểu; nó không nhận biểu thức tạo đối tượng. Hãy khai báo một class hoặc interface có tên làm nhánh trực tiếp nếu cần thêm một nhánh.

**Cho rằng lambda có thể triển khai bất kỳ interface nào.** Lambda chỉ tương thích với functional interface. Một sealed interface không thể đóng vai trò functional interface mục tiêu; hãy xác định xem nhánh có thực sự cần bị đóng hay cần được mở.

**Đánh dấu nhánh trực tiếp là `final` rồi mong anonymous class mở rộng nhánh đó.** `final` cấm mọi kiểu con. Nếu thiết kế cần cho phép các triển khai tùy biến, hãy cân nhắc một kiểu con trực tiếp `non-sealed` với tên rõ ràng.

**Dùng `non-sealed` mà không cân nhắc hệ quả.** Từ khi một nhánh được mở, mã khác có thể bổ sung kiểu con mà sealed parent không liệt kê trực tiếp. Chỉ mở nhánh khi đây là phần mở rộng mong muốn của API.

**Nhầm sealed với việc cấm mọi kiểu con.** Sealed không loại bỏ kế thừa; nó kiểm soát các kiểu con trực tiếp. Các nhánh `non-sealed` có thể tiếp tục mở rộng, còn `final` thì đóng và `sealed` thì tiếp tục kiểm soát.

## 7. Quy trình quyết định

1. Xác định kiểu nào là sealed parent và đọc danh sách `permits`.
2. Với mỗi kiểu con trực tiếp, kiểm tra rằng kiểu đó có tên và được khai báo `final`, `sealed` hoặc `non-sealed` theo đúng thiết kế.
3. Nếu cần lambda, kiểm tra kiểu mục tiêu có phải functional interface và không bị sealed hay không.
4. Nếu cần anonymous class, kiểm tra kiểu mà anonymous class trực tiếp mở rộng hoặc triển khai có phải nhánh mở hay không.
5. Khi cần mở rộng sealed hierarchy, tạo một nhánh trực tiếp có tên và đánh dấu `non-sealed` có chủ đích.
6. Biên dịch bằng JDK 17+ để phát hiện vi phạm quy tắc sealed; sau đó chạy chương trình và đối chiếu stdout.

## Ghi nhớ

Anonymous class và lambda không thể vượt qua ranh giới của sealed hierarchy. Anonymous class không thể là kiểu con trực tiếp của một sealed type; lambda không thể nhắm tới sealed interface vì sealed interface không phải functional interface. Cách mở rộng hợp lệ là khai báo một kiểu con trực tiếp có tên, cho phép kiểu đó là `non-sealed` khi thực sự muốn hỗ trợ thêm các triển khai, rồi dùng anonymous class hoặc lambda với nhánh mở ấy.