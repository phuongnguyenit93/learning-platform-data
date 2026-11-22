# Quan hệ bộ nhớ sau khi Future.get hoàn tất

## 1. Vì sao nhận kết quả còn là một vấn đề về bộ nhớ?

Một tác vụ chạy ở luồng khác có thể vừa tính giá trị trả về vừa ghi vào một đối tượng. Khi luồng gọi tiếp tục, làm sao biết nó có quyền quan sát các ghi đó?

Không thể trả lời chỉ bằng “máy đã chạy xong từ lâu”. Java có mô hình bộ nhớ quy định quan hệ giữa các hành động ở nhiều luồng. Muốn trao đổi dữ liệu đáng tin, chương trình cần một quan hệ đồng bộ được bảo đảm, không chỉ một khoảng chờ do người viết đoán.

`Future.get()` có hai vai trò liên quan:

- Chờ và nhận kết quả hoặc trạng thái kết thúc của một lần tính toán.
- Tạo điểm trao đổi dữ liệu có hợp đồng bộ nhớ giữa công việc bất đồng bộ và bên lấy kết quả.

Trong bài, đường chính là **get trả kết quả bình thường của tác vụ tương ứng**. Các đường timeout, bị ngắt và hủy phải xét riêng; không dùng câu “get đã kết thúc” một cách mơ hồ để suy ra toàn bộ mã tác vụ đã chạy xong.

Đây là kiến thức còn áp dụng trong Java hiện nay. Ví dụ hoàn chỉnh tương thích Java 17 trở lên.

## 2. Happens-before: trước theo hợp đồng, không chỉ trước trên đồng hồ

Quan hệ xảy ra-trước (happens-before) giúp quy định khả năng quan sát các hành động bộ nhớ giữa luồng. Nếu một phép ghi W xảy ra-trước một phép đọc R có liên quan, cùng với các điều kiện của chương trình, đó là cơ sở để lập luận về giá trị R được thấy.

Không hiểu happens-before đơn giản là “câu lệnh này chắc chắn có timestamp nhỏ hơn câu lệnh kia”. Nó là quan hệ trong mô hình bộ nhớ; Java cho phép tối ưu hóa miễn là hành vi quan sát vẫn tuân theo mô hình đó.

Hai quy tắc cần dùng:

1. Trong cùng luồng, thứ tự chương trình tạo quan hệ xảy ra-trước thích hợp giữa các hành động.
2. Quan hệ này có tính bắc cầu: nếu A xảy ra-trước B và B xảy ra-trước C, thì A xảy ra-trước C.

Khi thêm quy tắc của một công cụ đồng bộ, có thể nối lập luận từ luồng ghi sang luồng đọc. [JLS 17.4.5: Happens-before Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

Một điểm cần phân biệt: **nhìn thấy dữ liệu** không đồng nghĩa **không có hai bên cùng sửa dữ liệu**. Happens-before giúp thiết lập thứ tự và khả năng quan sát; khóa hoặc chiến lược sở hữu dữ liệu còn giúp bảo vệ các thao tác cần loại trừ nhau.

## 3. Hợp đồng của Future và chuỗi giao việc hai chiều

Tài liệu Future quy định các hành động trong công việc bất đồng bộ xảy ra-trước các hành động sau lời `Future.get()` tương ứng ở luồng khác. [Future: Memory consistency effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

ExecutorService còn cung cấp chiều đưa dữ liệu vào: các hành động ở luồng gọi trước khi giao Runnable/Callable xảy ra-trước các hành động của tác vụ đó. Sau đó, hành động của tác vụ xảy ra-trước việc nhận kết quả qua get. [ExecutorService: Memory consistency effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Ghép lại thành mô hình:

```text
Luồng gọi:
  chuẩn bị đầu vào
       ↓ xảy ra-trước qua việc giao tác vụ
Luồng thực thi:
  đọc đầu vào → tính toán → ghi dữ liệu kết quả
       ↓ xảy ra-trước qua get tương ứng
Luồng gọi:
  get trả kết quả bình thường → đọc dữ liệu đã được công bố
```

Vì vậy, trong một mô hình “một bên chuẩn bị đầu vào, tác vụ xử lý, bên gọi chỉ đọc sau get”, không phải thêm `volatile` cho mọi trường chỉ vì có hai luồng. Cần chứng minh đúng ranh giới bàn giao và bảo đảm không có truy cập đồng thời trái hợp đồng.

Hợp đồng này cũng không bị mất nếu tác vụ đã hoàn thành trước khi nơi gọi bắt đầu get. Get không cần phải thực sự làm luồng ngủ thì mới có ý nghĩa đồng bộ.

## 4. Ví dụ đầy đủ với các trường không volatile

Chương trình có một đối tượng đầu vào được chuẩn bị trước khi submit. Tác vụ đọc nó, tạo kết quả và ghi thêm dữ liệu vào một đối tượng báo cáo dùng chung. `main` chỉ đọc báo cáo sau khi get trả về bình thường.

Các trường của `Input` và `Report` cố ý là trường thông thường. Đây là ví dụ về bàn giao theo từng giai đoạn, không phải ví dụ cho phép sửa tùy ý từ nhiều luồng.

Lưu thành `FutureMemoryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureMemoryDemo {
    static final class Input {
        int left;
        int right;
    }

    static final class Report {
        int total;
        String description;
        int[] values;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        Input input = new Input();
        input.left = 20;
        input.right = 22;
        Report report = new Report();

        try {
            Future<Report> future = pool.submit(() -> {
                report.total = input.left + input.right;
                report.description = "computed";
                report.values = new int[] {input.left, input.right};
                return report;
            });

            Report received = future.get(10, TimeUnit.SECONDS);
            System.out.println("same report: " + (received == report));
            System.out.println("total: " + report.total);
            System.out.println("description: " + report.description);
            System.out.println("values: "
                    + report.values[0] + "," + report.values[1]);
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Executor did not terminate");
                    }
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 FutureMemoryDemo.java
java FutureMemoryDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
same report: true
total: 42
description: computed
values: 20,22
```

### Lập luận theo từng bước

1. `main` ghi `input.left` và `input.right` trước khi submit. Việc giao tác vụ thiết lập chiều đưa đầu vào đến tác vụ.
2. Sau submit, `main` không sửa các trường input nữa trong khi tác vụ dùng chúng.
3. Chỉ tác vụ ghi các trường report trong giai đoạn tính toán.
4. Lời get có thời hạn trả về bình thường; nếu hết hạn hoặc tác vụ lỗi, chương trình không đi vào các dòng in báo cáo như thể đã thành công.
5. Các ghi của tác vụ được quan sát sau get: tổng, chuỗi mô tả và các phần tử mảng.
6. Cùng một đối tượng report được nhận; get không tạo bản sao sâu. Hợp đồng bộ nhớ bao phủ việc công bố các ghi thích hợp, không chỉ bản thân tham chiếu trả về.

Một lần chạy cho kết quả đúng là kiểm chứng mã ví dụ, không phải bằng chứng duy nhất cho quy tắc Java Memory Model. Cơ sở bảo đảm nằm ở hợp đồng API và mô hình bộ nhớ. Ngược lại, một chương trình thiếu đồng bộ có thể in đúng hàng nghìn lần mà vẫn chưa được chứng minh đúng.

## 5. Vì sao ví dụ không cần volatile nhưng không cho phép mọi truy cập?

Tính đúng của ví dụ dựa vào **thứ tự sử dụng dữ liệu**:

```text
input:  main ghi → submit → tác vụ đọc
report: tác vụ ghi → get thành công → main đọc
```

Nếu `main` sửa input ngay sau submit trong khi tác vụ đang đọc, quan hệ từ phần chuẩn bị trước submit không tự bảo vệ lần sửa mới. Nếu main đọc report trước get trong khi tác vụ đang ghi, ranh giới nhận kết quả chưa được dùng cho phép đọc đó.

Đoạn minh họa sau là một thay đổi **không an toàn nếu không có đồng bộ bổ sung**; nó không phải chương trình nên chạy để học bằng cách đoán output:

```java
Future<?> future = pool.submit(() -> report.total = 42);
int premature = report.total; // Có thể đọc trong khi tác vụ còn ghi.
future.get();
```

Lời get đặt sau không sửa ngược tính đúng của phép đọc đã xảy ra trước nó. Muốn dựa vào hợp đồng Future cho phép đọc đó, chuyển phép đọc tới sau get thành công hoặc dùng một giao thức đồng bộ phù hợp khác.

`volatile` cũng không phải giải pháp tự động cho toàn bộ một đối tượng phức tạp. Cần xác định dữ liệu nào là cờ công bố, dữ liệu nào được bảo vệ, và liệu các thao tác nhiều bước có cần tính nguyên tử hay không.

## 6. Get không loại bỏ tranh chấp giữa các tác vụ

Giả sử hai tác vụ cùng thực hiện:

```java
counter.value++;
```

Đây là minh họa một thao tác đọc-sửa-ghi, không phải một phép tăng nguyên tử được bảo đảm cho trường int thông thường. Hai tác vụ có thể đọc cùng giá trị cũ rồi cùng ghi một giá trị mới, làm mất một lần tăng.

Dù main chờ cả hai Future xong rồi đọc bộ đếm, get cũng không khôi phục lần cập nhật đã mất. Nó nối kết quả các tác vụ về phía người đọc, không làm hai tác vụ có thứ tự trước-sau hoặc loại trừ nhau khi chúng đang chạy.

Cách thiết kế dễ lập luận hơn cho một phép tổng hợp:

- Mỗi tác vụ tính một phần kết quả trong dữ liệu riêng.
- Mỗi Future trả phần kết quả đó.
- Main nhận các kết quả và tổng hợp theo thứ tự của chính main.

Nếu thực sự cần chia sẻ một bộ đếm đang được nhiều tác vụ tăng, dùng công cụ nguyên tử, khóa hoặc giải pháp tổng hợp phù hợp với yêu cầu. Chọn công cụ theo thao tác cần bảo vệ; một bộ đếm nguyên tử không tự làm cả chuỗi cập nhật nhiều đối tượng trở thành một giao dịch.

## 7. Get của tác vụ nào thì lập luận theo tác vụ đó

Giả sử tác vụ A và B cùng được gửi vào một nhóm nhiều luồng. `futureA.get()` thành công không tự là bằng chứng B đã hoàn tất. Các ghi chỉ do B thực hiện vẫn cần đường đồng bộ của B hoặc một quan hệ phụ thuộc rõ ràng khác.

Không suy “đều ở cùng executor nên chờ một Future là xong tất cả”. Cũng không dựa vào thời gian chờ đủ lâu hay việc thấy một thông báo log từ công việc khác để thay hợp đồng đồng bộ.

Nếu A tạo thêm một luồng riêng hoặc giao tiếp một công việc con rồi trả về trước khi công việc đó xong, Future của A chủ yếu theo dõi phần thực thi mà nó đại diện. Không mặc định get của A chờ mọi hoạt động con được tạo ra. Cần thiết kế ranh giới hoàn tất để bao gồm kết quả cần thiết, hoặc thu nhận riêng các công việc con.

Tính bắc cầu cho phép nối các quan hệ được xác định rõ, nhưng không cho phép tự thêm một quan hệ chỉ vì hai công việc có liên quan về nghiệp vụ.

## 8. Timeout, ngắt, thất bại và hủy cần được xét riêng

| Cách lời get kết thúc | Điều cần hiểu trước khi đọc dữ liệu |
|---|---|
| Trả kết quả bình thường | Có thể lập luận công bố dữ liệu của tác vụ tương ứng theo hợp đồng, với các điều kiện sở hữu/không tranh chấp phù hợp |
| Ném TimeoutException | Chưa lấy được kết quả trong hạn; tác vụ có thể còn đang ghi |
| Ném InterruptedException | Luồng chờ bị ngắt; không đồng nghĩa tác vụ đã xong |
| Ném ExecutionException | Tác vụ đã báo thất bại; dữ liệu nghiệp vụ có thể mới được cập nhật một phần |
| Ném CancellationException | Future đã hủy; mã tác vụ có thể còn phản hồi ngắt hoặc dọn dẹp |

Không áp dụng câu “sau get đọc được trạng thái cuối” cho một lời chờ vừa timeout. Cũng không đọc trường thông thường do tác vụ bị hủy còn đang sửa rồi cho rằng isDone/isCancelled đã thay cho mọi đồng bộ cần thiết.

Ở đường thất bại, phải phân biệt **khả năng quan sát một ghi đã xảy ra** với **tính hợp lệ của toàn bộ kết quả nghiệp vụ**. Một tác vụ có thể ghi tổng rồi ném lỗi trước khi ghi mô tả; dù biết lần tính toán thất bại, không được coi đối tượng dở dang là báo cáo thành công. Bài dùng đường get trả bình thường để trình bày mẫu bàn giao dữ liệu hoàn chỉnh; nếu cần đọc trạng thái chẩn đoán khi thất bại, hãy định nghĩa rõ trạng thái nào được công bố và điều kiện nào bảo vệ nó.

Với hủy, một tín hiệu dọn dẹp riêng như latch hoặc giao thức kết thúc được thiết kế đúng có thể cần thiết nếu nơi gọi phải biết mã tác vụ đã đi qua điểm dọn tài nguyên. Future cancelled không tự hoàn tác các ghi trước đó hoặc bảo đảm tất cả các ghi về sau đã dừng.

## 9. Kết quả đã được công bố vẫn có thể bị sửa về sau

Trong ví dụ, `Report` chứa một mảng có thể thay đổi. Sau get, nếu chỉ main dùng report thì có thể tổ chức quyền sở hữu đơn giản. Nếu sau đó main chuyển report cho một luồng khác, cần một lần công bố phù hợp cho luồng nhận mới.

Nếu tác vụ hoặc một bên khác tiếp tục sửa `report.values` sau khi get trả về, get không bảo vệ các lần sửa mới. Cần lựa chọn như:

- Kết quả bất biến, bao gồm cấu trúc dữ liệu bên trong.
- Sao chép ở ranh giới chuyển giao khi phù hợp.
- Quyền sở hữu độc quyền sau hoàn tất.
- Đồng bộ rõ ràng cho dữ liệu còn chia sẻ và thay đổi.

Một record có thể giúp mô tả kết quả, nhưng record chứa một mảng vẫn giữ tham chiếu tới mảng; nó không tự làm nội dung mảng bất biến. Không đánh đồng “trường final” với “toàn bộ đồ thị đối tượng không thể thay đổi”.

## 10. Những cách thay thế không nên suy diễn tùy tiện

`Thread.sleep()` không tự tạo một quan hệ đồng bộ cho các trường thông thường giữa hai luồng. Ngủ lâu hơn chỉ thay đổi lịch chạy có thể quan sát, không thay hợp đồng công bố. Tương tự, `Thread.yield()` không phải cơ chế bàn giao kết quả. [JLS: Sleep and Yield](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.3).

`isDone()` là một phép hỏi trạng thái và bao gồm cả thất bại/hủy. Nếu mục tiêu là lấy kết quả và dựa vào hợp đồng bộ nhớ của get, hãy dùng get tương ứng thay vì vòng lặp bận trên isDone rồi đọc dữ liệu chia sẻ. Một triển khai có thể dùng volatile bên trong, nhưng mã ứng dụng nên lập luận bằng hợp đồng công khai phù hợp thay vì sao chép giả định từ chi tiết triển khai.

Tài liệu gói `java.util.concurrent` mô tả các bảo đảm bộ nhớ của nhiều công cụ như executor, Future, khóa và bộ đồng bộ. Chọn công cụ đúng với ranh giới trao đổi: không cần tự tạo giao thức cờ bận khi một Future đã biểu diễn đúng lần tính toán cần chờ. [java.util.concurrent: Memory consistency properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html).

## 11. Tự kiểm tra và thực hành

1. Vì sao main đọc được trường report.total không volatile sau get thành công trong ví dụ? **Các ghi của tác vụ được công bố qua get tương ứng, và không có bên khác sửa cạnh tranh sau đó.**
2. Thêm get sau một phép đọc sớm có làm phép đọc sớm trở nên đúng không? **Không.** Phải đặt phép đọc tại ranh giới đã có bảo đảm hoặc đồng bộ nó bằng cách khác.
3. Chờ hai Future có sửa được việc hai tác vụ cùng tăng một biến int sai cách không? **Không.** Lần cập nhật mất do tranh chấp không được khôi phục bởi việc chờ.
4. Một Future thành công có nghĩa mọi tác vụ trong cùng executor đều xong không? **Không.** Cần quan hệ tương ứng với công việc cần quan sát.
5. Một Future hủy rồi isDone trả true có chứng minh tác vụ không còn ghi dữ liệu không? **Không.** Hủy và kết thúc thực tế cần phân biệt.

Thực hành: đổi ví dụ để Callable xây dựng một đối tượng kết quả mới hoàn toàn trong thân tác vụ, rồi trả nó về; main chỉ dùng đối tượng nhận từ get. Sau đó thay mảng kết quả bằng một danh sách bất biến được tạo sau khi tính xong. Giải thích phần nào giúp công bố dữ liệu giữa luồng, phần nào giúp ngăn các lần sửa về sau. Không viết bài kiểm tra kỳ vọng một chương trình thiếu đồng bộ phải luôn in sai: hành vi đúng trong một lần chạy không chứng minh nó có bảo đảm.
