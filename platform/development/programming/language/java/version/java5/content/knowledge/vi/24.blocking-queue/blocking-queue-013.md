# Quan hệ bộ nhớ khi chuyển dữ liệu qua hàng đợi

Một luồng tạo đối tượng, gán đầy đủ dữ liệu rồi chuyển cho một luồng khác. Câu hỏi không chỉ là “luồng nào lấy được phần tử?”, mà còn là: **bên nhận có được bảo đảm nhìn thấy những giá trị bên gửi đã ghi không?**

`BlockingQueue` vừa phối hợp việc gửi/nhận phần tử, vừa cung cấp một quan hệ bộ nhớ giúp chuyển dữ liệu giữa các luồng. Hiểu đúng quan hệ này giúp tránh hai sai lầm ngược nhau: thêm `volatile` vào mọi trường không cần thiết, hoặc cho rằng đối tượng đã vào hàng đợi thì mọi lần sửa sau đó đều an toàn.

## 1. Vì sao cần một quan hệ bộ nhớ?

Trong chương trình nhiều luồng, việc một phép ghi “đã chạy trước theo đồng hồ” chưa đủ để chứng minh một phép đọc ở luồng khác được đồng bộ hóa với phép ghi đó. Mô hình bộ nhớ Java (Java Memory Model, JMM) quy định các giá trị mà phép đọc có thể quan sát.

Quan hệ **happens-before** mô tả một thứ tự có ý nghĩa đối với khả năng nhìn thấy dữ liệu và các ràng buộc sắp xếp thao tác. Nó không phải yêu cầu mọi câu lệnh phải thực thi tuần tự trên một bộ xử lý. Định nghĩa và tính bắc cầu nằm trong [JLS 17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

Ví dụ không an toàn dưới đây chỉ để phân tích, không phải mã nên đưa vào ứng dụng:

```java
// Hai trường dùng chung thông thường, không có cơ chế đồng bộ hóa.
Message shared;
boolean ready;

// Luồng gửi:
shared = new Message();
shared.text = "ready";
ready = true;

// Luồng nhận:
while (!ready) {
    // Chờ bằng cách đọc một biến thông thường.
}
System.out.println(shared.text);
```

Giả sử các đoạn trên nằm ở hai luồng cùng truy cập các trường của một đối tượng dùng chung. Không có quan hệ đồng bộ hóa phù hợp: vòng chờ có thể không quan sát được cập nhật, và cờ thông thường không phải cơ chế công bố dữ liệu. Thêm `sleep()` hoặc `yield()` không sửa được lập luận bộ nhớ này.

Giải pháp là dùng một cơ chế có hợp đồng bộ nhớ rõ ràng; với mô hình gửi công việc, hàng đợi thường là cơ chế tự nhiên.

## 2. Quy tắc của BlockingQueue

Những hành động trong một luồng **trước khi đưa đối tượng vào hàng đợi** happens-before những hành động trong luồng khác **sau khi truy cập hoặc lấy đối tượng đó từ hàng đợi**. Đây là hợp đồng ở cấp API, không yêu cầu người dùng biết lớp cụ thể dùng khóa hay cơ chế nội bộ nào. Xem [BlockingQueue — Memory consistency effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Với một lần bàn giao bằng `put` và `take`, có thể lập luận:

```text
Luồng gửi                               Luồng nhận
1. Ghi message.id = 1
2. Ghi message.text = "ready"
3. Ghi message.values[0] = 7
4. queue.put(message)  ───────────────►  5. message = queue.take()
                                         6. Đọc các trường của message

Các phép ghi 1–3 happens-before các phép đọc ở bước 6.
Điều kiện thiết kế: không có luồng khác đồng thời sửa các dữ liệu đó.
```

Đây là **công bố an toàn (safe publication)** qua hàng đợi. Các trường của thông điệp không phải tự mang `volatile` chỉ để truyền trạng thái đã chuẩn bị trước lần gửi này.

Quy tắc cũng áp dụng cho dữ liệu đã chuẩn bị trong những đối tượng mà thông điệp tham chiếu tới, chẳng hạn phần tử của mảng. Phạm vi không bị giới hạn ở giá trị tham chiếu của chính phần tử hàng đợi. Tuy nhiên, các đối tượng con không được có bên khác tiếp tục sửa thiếu đồng bộ.

Phép chuyển bằng `offer` chỉ tạo lần bàn giao khi thật sự thêm thành công. Nếu `offer` trả `false`, chưa có thông điệp được chuyển từ lần gọi đó. Tương tự, `poll` trả `null` không cho bên nhận một phần tử để dựa vào quan hệ bàn giao của phần tử ấy.

## 3. Chương trình chạy đầy đủ: bàn giao rồi nhận phản hồi

Lưu thành `QueueMemoryDemo.java`. Các trường trong `Message` cố ý là trường thông thường để làm rõ tác dụng của hàng đợi.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueMemoryDemo {
    static class Message {
        int id;
        String text;
        int[] values;
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> requests = new ArrayBlockingQueue<>(1);
        BlockingQueue<Message> replies = new ArrayBlockingQueue<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message received = requests.take();
                System.out.println("consumer: " + received.id + ", "
                        + received.text + ", " + received.values[0]);

                received.text = "handled";
                received.values[0] += 10;
                replies.put(received);
                // No further access to the message after handoff.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");
        consumer.start();

        // Create and populate the message after starting the consumer.
        Message sent = new Message();
        sent.id = 1;
        sent.text = "ready";
        sent.values = new int[] {7};
        requests.put(sent);

        // Do not inspect or modify sent while the consumer owns it.
        Message returned = replies.take();
        System.out.println("same reference: " + (returned == sent));
        System.out.println("producer sees: " + returned.text + ", "
                + returned.values[0]);

        consumer.join();
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 QueueMemoryDemo.java
java QueueMemoryDemo
```

Stdout của lượt chạy bình thường, không có tác nhân bên ngoài ngắt luồng:

```text
consumer: 1, ready, 7
same reference: true
producer sees: handled, 17
```

Phân tích hai chiều:

1. Luồng gửi tạo và điền `sent` **sau** khi đã gọi `consumer.start()`. Vì vậy, không thể dùng riêng bảo đảm bộ nhớ của `Thread.start()` để giải thích các giá trị thông điệp này.
2. Việc chuẩn bị `sent` xảy ra trước `requests.put(sent)`; bên tiêu thụ đọc sau `requests.take()`. Đây là chiều công bố thứ nhất.
3. Sau khi nhận, bên tiêu thụ là bên duy nhất được phép sửa thông điệp: đổi `text`, tăng phần tử mảng, rồi đưa vào `replies`.
4. Luồng gửi không đọc hoặc sửa thông điệp trong lúc bên tiêu thụ sở hữu nó. Sau `replies.take()`, nó nhận lại quyền sử dụng và quan sát các cập nhật trước `replies.put`.
5. `consumer.join()` nằm sau các phép đọc kết quả. Nó phục vụ chờ kết thúc luồng trong ví dụ, không phải lý do các phép đọc kết quả trước đó được bảo đảm.

Dòng `same reference: true` cho thấy hàng đợi chuyển **tham chiếu tới cùng đối tượng**, không tự sao chép đối tượng hay mảng bên trong.

Trong ví dụ có đúng một yêu cầu và một phản hồi nên kết quả khớp nhau. Hệ thống có nhiều yêu cầu đồng thời cần thêm định danh để ghép phản hồi với yêu cầu, cùng chính sách thời hạn và xử lý hủy; quan hệ bộ nhớ không tự cung cấp giao thức đó.

## 4. Vì sao không được sửa tùy ý sau khi gửi?

Đoạn sau chỉ minh họa lỗi quyền sở hữu:

```java
message.text = "before";
queue.put(message);
message.text = "after";  // Không an toàn nếu bên nhận đang đọc text.
```

Phép ghi `"after"` nằm sau lần gửi, nên không được bao phủ bởi quan hệ công bố trước lần gửi đó. Nếu bên nhận cũng đọc mà không có cơ chế đồng bộ hóa bổ sung, xuất hiện truy cập xung đột không được sắp thứ tự bởi happens-before, tức tranh chấp dữ liệu (data race). Không được khẳng định bên nhận chắc chắn thấy `"before"` hoặc chắc chắn thấy `"after"`.

Ngay cả khi lần gửi đã trả về, bên nhận có thể đã bắt đầu xử lý. `put()` thành công không hứa rằng bên tiêu thụ vẫn chưa chạy, cũng không hứa rằng nó đã xử lý xong.

Ba cách thiết kế phổ biến:

| Thiết kế | Quy tắc cần giữ |
|---|---|
| Thông điệp bất biến | Khởi tạo đầy đủ, gửi rồi không sửa; dữ liệu tham chiếu bên trong cũng cần được bảo vệ khỏi thay đổi |
| Bàn giao quyền sở hữu | Bên gửi ngừng truy cập dữ liệu có thể thay đổi sau khi gửi; bên nhận sở hữu cho tới lần bàn giao tiếp theo |
| Trạng thái thực sự dùng chung | Mọi bên phối hợp bằng khóa, trường `volatile`, kiểu nguyên tử hoặc cơ chế phù hợp với từng bất biến |

Ví dụ chọn cách thứ hai để thấy việc sửa có kiểm soát qua hai lượt bàn giao. Khi có thể, thông điệp bất biến thường giảm số quy tắc mà người đọc cần theo dõi.

Một `record` có trường là `List` hoặc mảng chưa tự là bất biến sâu: thành phần tham chiếu không bị gán lại không có nghĩa nội dung đối tượng được tham chiếu không thể đổi. Khi thiết kế thông điệp bất biến, cần cân nhắc sao chép phòng vệ và tính bất biến của các phần tử con.

## 5. Nhìn thấy dữ liệu khác với thao tác nguyên tử

Quan hệ bộ nhớ của hàng đợi không làm một chuỗi thao tác trên đối tượng trở thành không thể xen kẽ.

Giả sử cùng một đối tượng `Counter` bị gửi cho hai bên nhận bằng hai lần thêm vào hàng đợi. Cả hai cùng thực hiện:

```java
counter.value++;
```

Phép tăng gồm đọc, tính và ghi; hai luồng có thể ghi đè kết quả của nhau. Việc công bố ban đầu an toàn không làm phép tăng sau đó trở thành nguyên tử. Ngay cả khai báo riêng `value` là `volatile` cũng không biến `value++` thành một phép cập nhật nguyên tử; cần kiểu nguyên tử hoặc khóa nếu muốn cùng sửa.

Cách tránh trong mô hình bàn giao là không phát cùng một đối tượng có thể thay đổi cho nhiều bên như thể mỗi bên đều sở hữu độc quyền. Nếu cần phát cho nhiều bên, dùng dữ liệu bất biến hoặc bản sao độc lập.

Tương tự, việc `queue.isEmpty()` trả về một kết quả không phải tín hiệu hoàn thành nghiệp vụ. Nó không chứng minh dữ liệu trong một biến dùng chung khác đã sẵn sàng, và hàng đợi rỗng vẫn có thể có công việc đang được xử lý bên ngoài hàng đợi. Dựa vào phần tử hoặc cơ chế xác nhận cụ thể thay vì suy diễn từ kích thước.

## 6. Quan hệ có hướng và có tính bắc cầu

Chiều gửi yêu cầu không tự tạo chiều công bố kết quả:

```text
Gửi → nhận yêu cầu: bảo đảm dữ liệu chuẩn bị trước khi gửi.
Xử lý → bên gửi đọc kết quả: cần một quan hệ tiếp theo.
```

Trong ví dụ, hàng đợi `replies` cung cấp quan hệ tiếp theo. Các lựa chọn khác tùy mô hình có thể là `Future.get()`, một chốt đếm được dùng đúng giao thức, hoặc `join()` khi muốn chờ cả luồng kết thúc. Tổng quan các bảo đảm này có trong [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

Tính bắc cầu hữu ích với dây chuyền xử lý:

```text
A chuẩn bị dữ liệu
  → A gửi cho B qua queue1
  → B nhận và biến đổi dữ liệu
  → B gửi cho C qua queue2
  → C nhận và đọc dữ liệu
```

Nếu mỗi ranh giới được bàn giao đúng cách và không có bên ngoài sửa thiếu đồng bộ, các phép ghi trước đó được nối qua các quan hệ happens-before tới phép đọc cuối. C không cần biết chi tiết triển khai của hai hàng đợi.

Nhưng một đường đi an toàn không sửa được một đường truy cập khác thiếu đồng bộ. Nếu một biến toàn cục vẫn trỏ tới cùng mảng và một luồng ngoài dây chuyền sửa mảng tùy ý, giao thức bàn giao trong dây chuyền không đủ bảo vệ dữ liệu.

## 7. Những suy luận cần tránh

- **“Chỉ an toàn khi bên nhận thật sự bị block.”** Sai. Hợp đồng công bố vẫn áp dụng khi phần tử đã sẵn có và `take()` lấy ngay; nó không phụ thuộc việc luồng có phải ngủ chờ hay không.
- **“Đã đọc bằng `peek()` thì tôi sở hữu phần tử.”** Sai. Truy cập phần tử qua hàng đợi có bảo đảm bộ nhớ tương ứng, nhưng `peek()` không lấy nó ra; bên tiêu thụ khác vẫn có thể nhận và sửa theo giao thức của ứng dụng. Nhìn thấy dữ liệu không đồng nghĩa quyền truy cập độc quyền.
- **“Hàng đợi bảo vệ toàn bộ đối tượng mãi về sau.”** Sai. Nó bảo vệ thao tác hàng đợi và lần công bố liên quan, không tự đồng bộ mọi phương thức trên đối tượng.
- **“Gửi lần thứ hai cùng tham chiếu sẽ sửa lần đầu.”** Sai. Lần gửi sau không làm các truy cập trước đó ở bên nhận trở thành an toàn hồi tố.
- **“Chạy thử nhiều lần đúng là đã chứng minh không có data race.”** Sai. Kết quả chạy là bằng chứng thực nghiệm hữu ích; chứng minh bộ nhớ phải dựa vào quan hệ và hợp đồng đồng bộ hóa.

Không mô tả cơ chế này đơn giản là “đẩy hết cache về RAM”. JMM quy định hành vi quan sát được; JVM và phần cứng có thể dùng nhiều cách hiện thực khác nhau miễn đáp ứng hợp đồng.

## 8. Tự kiểm tra

1. Trường `message.text` không `volatile`, được ghi trước `put`, đọc sau `take` và không ai sửa thêm: có cần thêm `volatile` chỉ cho lần bàn giao này không? — Không; hàng đợi đã cung cấp quan hệ bộ nhớ.
2. Bên gửi sửa mảng sau `put`, trong lúc bên nhận đọc: hàng đợi có tự bảo vệ không? — Không.
3. Bên nhận ghi kết quả vào đối tượng, bên gửi đọc ngay sau `put` trả về: đã đủ chưa? — Chưa; cần cơ chế báo hoàn tất có quan hệ bộ nhớ phù hợp.
4. Hai bên nhận cùng tăng một trường thông thường có an toàn chỉ vì đã nhận qua hàng đợi không? — Không; công bố an toàn khác với cập nhật nguyên tử.
5. Trong ví dụ, điều gì bảo đảm bên gửi thấy 17 trước khi gọi `join()`? — Chuỗi ghi ở bên tiêu thụ → `replies.put` → `replies.take` → đọc kết quả.
