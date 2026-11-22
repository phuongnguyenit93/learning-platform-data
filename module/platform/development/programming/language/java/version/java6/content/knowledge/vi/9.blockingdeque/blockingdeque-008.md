# Bảo đảm nhìn thấy dữ liệu khi chuyển phần tử giữa các luồng

## 1. Vấn đề: nhận được tham chiếu chưa đủ để hiểu tính đúng đắn

Một luồng chuẩn bị công việc rồi chuyển cho luồng khác xử lý là tình huống rất phổ biến:

1. Tạo đối tượng công việc.
2. Gán dữ liệu vào các trường.
3. Gửi đối tượng vào hàng đợi.
4. Luồng khác lấy ra và đọc dữ liệu.

Điều cần bảo đảm không chỉ là “hai luồng cùng giữ được một tham chiếu”. Bên nhận còn phải đọc được trạng thái đã chuẩn bị trước khi gửi.

Trong lập trình đồng thời Java, **tính nhìn thấy dữ liệu (visibility)** trả lời câu hỏi: một lần ghi ở luồng này có được luồng khác quan sát đúng theo các quy tắc của mô hình bộ nhớ không? Việc luồng A chạy trước về thời gian thực không tự tạo mọi bảo đảm cần thiết cho luồng B.

`BlockingDeque` cung cấp một kênh chuyển giao có hợp đồng bộ nhớ rõ ràng. Bài này tập trung vào hợp đồng đó, cách áp dụng và ranh giới của nó; không phụ thuộc vào suy đoán về bộ nhớ đệm CPU hay chi tiết khóa bên trong một phiên bản JVM.

Các ví dụ chạy bằng Java 17+. `BlockingDeque` xuất hiện từ Java 6 và các quy tắc sử dụng ở đây vẫn áp dụng trong Java hiện đại.

## 2. Hợp đồng happens-before của BlockingDeque

Theo [tài liệu BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html), các hành động của một luồng trước khi đưa một đối tượng vào deque có quan hệ `happens-before` với các hành động sau khi luồng khác truy cập hoặc lấy đối tượng đó ra.

Có thể đọc theo đường đi sau:

```text
Luồng gửi                           Luồng nhận

ghi dữ liệu vào message
        |
        v
putLast(message)  ---- chuyển ---->  takeFirst() nhận message
                                            |
                                            v
                                    đọc dữ liệu của message
```

`happens-before` là quan hệ thứ tự của mô hình bộ nhớ Java. Nó cho phép lập luận về tính nhìn thấy dữ liệu, thay vì hy vọng rằng một lần ghi “chắc đã kịp cập nhật”. Khi không có những lần ghi cạnh tranh về sau, bên nhận có thể đọc trạng thái đã được chuẩn bị trước khi gửi.

Ba điểm cần giữ rõ:

- Các lần ghi phải nằm **trước lần thêm thành công** đang dùng để chuyển giao.
- Bên nhận phải thực sự nhận hoặc truy cập phần tử qua kênh có bảo đảm phù hợp, rồi mới đọc dữ liệu.
- Việc chuyển qua đầu hay cuối quyết định thứ tự phần tử; nó không thay đổi bản chất bảo đảm bộ nhớ.

Thao tác không nhất thiết phải thật sự chặn luồng. `putLast` trên deque còn chỗ vẫn là một lần chuyển giao hợp lệ. `offerLast` trả `true` cũng vậy. Đừng nhầm “có cơ chế đồng bộ” với “bắt buộc phải đợi”.

## 3. Ví dụ đầy đủ: các trường thường vẫn được chuyển giao an toàn

Ví dụ cố ý dùng trường không có `volatile` và không có `final`, để thấy rằng bảo đảm đến từ đường chuyển giao qua deque. Sau khi gửi, bên gửi không sửa đối tượng nữa.

Lưu thành `DequePublicationDemo.java`:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;

public class DequePublicationDemo {
    static final class Message {
        int id;
        String text;
        int[] values;
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingDeque<Message> inbox = new LinkedBlockingDeque<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message received = inbox.takeFirst();
                System.out.println("id = " + received.id);
                System.out.println("text = " + received.text);
                System.out.println("sum = "
                        + (received.values[0] + received.values[1]));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();

        // Cac lan ghi nay xay ra SAU khi consumer da duoc start.
        Message message = new Message();
        message.id = 7;
        message.text = "ready";
        message.values = new int[] {10, 20};

        inbox.putLast(message);

        // Sau khi gui: khong sua message hay message.values nua.
        consumer.join();
    }
}
```

Biên dịch và chạy:

```shell
javac DequePublicationDemo.java
java DequePublicationDemo
```

Stdout trong lần chạy bình thường, không có yêu cầu ngắt từ bên ngoài:

```text
id = 7
text = ready
sum = 30
```

Phân tích đường bảo đảm:

1. Luồng `main` ghi `id`, `text`, tham chiếu `values` và các phần tử mảng.
2. Cũng luồng đó đưa `message` vào `inbox`.
3. Luồng `consumer` lấy đúng đối tượng ra bằng `takeFirst`.
4. Các lần đọc tiếp theo nhận được trạng thái đã chuẩn bị.

Bảo đảm bao gồm các lần ghi vào mảng trong ví dụ, không chỉ riêng giá trị tham chiếu `message.values`. Tuy nhiên, nó không biến mảng thành bất biến.

Việc khởi động `consumer` xảy ra trước các lần gán dữ liệu. Vì thế, không thể giải thích các lần gán này bằng quy tắc “ghi trước `Thread.start()`”. Đường chuyển giao qua deque mới là điểm cần quan sát trong ví dụ.

`join()` ở cuối chỉ giúp luồng chính chờ bên nhận kết thúc. Không cần chèn `sleep()` để “đợi dữ liệu cập nhật”.

## 4. Đọc quan hệ bảo đảm theo chuỗi

Trong [mô hình bộ nhớ Java, JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5), quan hệ `happens-before` có tính bắc cầu. Với ví dụ trên:

```text
ghi message.id = 7
    |
    | thứ tự trong luồng gửi
    v
đưa message vào deque
    |
    | hợp đồng chuyển giao của deque
    v
luồng nhận lấy message
    |
    | thứ tự trong luồng nhận
    v
đọc received.id
```

Chuỗi này là cách suy luận ở mức chương trình. Không cần tự thêm `synchronized` quanh hai lời gọi `putLast` và `takeFirst` chỉ để công bố dữ liệu đã chuẩn bị trước khi gửi.

Hai giới hạn về chuỗi bảo đảm rất dễ bỏ sót:

- Nếu một luồng thứ ba ghi dữ liệu mà luồng gửi chưa nhận dữ liệu đó bằng cơ chế đồng bộ đúng, việc luồng gửi chuyển một tham chiếu qua deque không tự sửa được lỗi ở giai đoạn trước.
- Nếu bên nhận đọc đối tượng qua một biến dùng chung khác **trước khi** lấy phần tử từ deque, không thể dùng lần lấy diễn ra sau đó để hợp thức hóa lần đọc trước.

Nói cách khác, phải theo dõi đường đi thật của dữ liệu và thứ tự thật của các lần đọc/ghi.

## 5. Ranh giới: deque an toàn không làm đối tượng tự an toàn

### 5.1. Không tự bảo đảm các lần sửa sau khi gửi

Đoạn sau chỉ minh họa lỗi, không phải chương trình độc lập:

```java
Message message = new Message();
message.id = 1;
message.text = "ready";

inbox.putLast(message);

// Loi thiet ke: ben nhan co the dang doc cung doi tuong.
message.id = 2;
message.text = "changed";
```

Bên gửi và bên nhận cùng giữ tham chiếu đến một đối tượng. Deque không sao chép đối tượng. Các lần ghi `id = 2` và `text = "changed"` nằm sau lần gửi, nên không được chuyển giao bởi chính lần gửi trước đó.

Nếu bên nhận đồng thời đọc các trường này mà không có thêm cơ chế phối hợp, chương trình có **tranh chấp dữ liệu (data race)**. Không được khẳng định hai trường luôn tạo thành một cặp trạng thái nhất quán.

Thêm `volatile` cho từng trường cũng không tự biến nhiều lần đọc/ghi thành một giao dịch chung. Nếu nghiệp vụ yêu cầu hai trường thay đổi cùng nhau, phải thiết kế một trạng thái bất biến để thay thế hoặc một vùng đồng bộ bảo vệ toàn bộ quy tắc đó.

### 5.2. Lấy ra không xóa mọi tham chiếu khác

`takeFirst()` gỡ phần tử khỏi deque. Nó không xóa biến `message` của bên gửi, không thu hồi các tham chiếu đang nằm trong bộ nhớ đệm khác và không cấm mã khác sửa đối tượng.

Vì vậy, “quyền sở hữu đối tượng được chuyển sang bên nhận” là **kỷ luật của ứng dụng**, không phải một hạn chế được hệ thống kiểu Java tự ép buộc.

Nếu cùng một đối tượng được đưa vào deque hai lần, hai luồng tiêu thụ có thể lấy hai phần tử nhưng vẫn cùng trỏ vào đối tượng đó. Hai phần tử không có nghĩa là hai bản sao dữ liệu.

### 5.3. Không bảo đảm chiều trả kết quả một cách tự động

Sau khi nhận, bên xử lý có thể tính một kết quả. Bên gửi không được đọc một trường kết quả thường rồi giả định rằng lần `putLast` ban đầu đã đồng bộ cả chiều ngược lại.

Một thiết kế hai chiều có thể dùng hai kênh:

```text
Luồng gọi                             Luồng xử lý

chuẩn bị request
requests.putLast(request) ----------> requests.takeFirst()
                                      tính result
responses.takeFirst() <------------- responses.putLast(result)
đọc result
```

Trong thiết kế này, lần gửi vào `responses` công bố dữ liệu kết quả. Khi có nhiều yêu cầu đồng thời, ứng dụng còn cần định danh tương quan hoặc cơ chế trả kết quả cho đúng bên gọi. Bảo đảm bộ nhớ không tự giải quyết việc định tuyến phản hồi.

## 6. Ba cách tổ chức dữ liệu sau chuyển giao

| Cách tổ chức | Quy tắc chính | Phù hợp khi |
| --- | --- | --- |
| Chuyển quyền sở hữu theo giai đoạn | Bên gửi không sửa sau khi gửi; một bên xử lý chịu trách nhiệm ở mỗi giai đoạn | Dữ liệu lớn, cần tránh sao chép nhưng kiểm soát được các tham chiếu |
| Gửi dữ liệu bất biến hoặc bản chụp độc lập | Chuẩn bị xong rồi không cho thay đổi phần dữ liệu được chia sẻ | Thông điệp, yêu cầu, sự kiện giữa các luồng |
| Chia sẻ đối tượng tiếp tục thay đổi | Mọi bên tuân thủ cùng cơ chế đồng bộ cho các lần đọc/ghi về sau | Trạng thái thực sự cần được nhiều luồng cập nhật |

Cách thứ nhất không cho phép bên gửi âm thầm sửa lại công việc. Cách thứ hai cần xem cả cấu trúc bên trong, không chỉ lớp bao ngoài. Cách thứ ba cần quy tắc rõ ràng, chẳng hạn cùng một khóa bảo vệ tất cả các trường thuộc một bất biến nghiệp vụ.

Không tự đồng bộ trên đối tượng deque rồi cho rằng đã bao phủ mọi truy cập dữ liệu phần tử. Nếu các bên khác không cùng dùng chính quy tắc khóa đó, các lần sửa đối tượng vẫn chưa được bảo vệ.

### Ví dụ bản chụp không đổi cấu trúc

`record` giúp biểu diễn thông điệp gọn gàng nhưng không tự làm dữ liệu lồng bên trong trở nên bất biến. Ví dụ sau dùng `List.copyOf` để tránh giữ trực tiếp danh sách có thể thay đổi của bên gửi.

Lưu thành `DequeSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.LinkedBlockingDeque;

public class DequeSnapshotDemo {
    record Job(String id, List<String> labels) {
        Job {
            Objects.requireNonNull(id, "id");
            labels = List.copyOf(labels);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingDeque<Job> inbox = new LinkedBlockingDeque<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Job job = inbox.takeFirst();
                System.out.println(job.id() + " -> " + job.labels());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();

        List<String> draftLabels = new ArrayList<>();
        draftLabels.add("draft");

        Job snapshot = new Job("invoice-42", draftLabels);
        inbox.putLast(snapshot);

        // Chi sua danh sach goc, khong sua danh sach trong snapshot.
        draftLabels.add("approved");

        consumer.join();
    }
}
```

Chạy bằng Java 17+:

```shell
javac DequeSnapshotDemo.java
java DequeSnapshotDemo
```

Stdout:

```text
invoice-42 -> [draft]
```

Kết quả không phụ thuộc vào việc bên nhận in trước hay sau lần thêm `"approved"`. `Job` đã giữ danh sách từ `List.copyOf`, không giữ trực tiếp `draftLabels`.

Theo [hợp đồng List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), danh sách kết quả không cho sửa cấu trúc và không phản ánh những lần đổi cấu trúc danh sách nguồn về sau. Việc này không phải sao chép sâu từng phần tử.

Trong ví dụ, phần tử là `String` bất biến. Nếu đổi thành `List<MutableLabel>`, sao chép danh sách vẫn giữ các tham chiếu đến `MutableLabel`; việc sửa một nhãn có thể tiếp tục là vấn đề. Khi cần bản chụp sâu, phải tự sao chép trạng thái có thể thay đổi.

Cũng cần hoàn tất việc tạo bản chụp trong khi bên tạo có quyền truy cập dữ liệu nguồn hợp lệ. `List.copyOf` không phải cách sửa lỗi một `ArrayList` đang bị luồng khác thay đổi không đồng bộ trong lúc sao chép.

## 7. Những kết quả nào thật sự tạo đường chuyển giao?

| Tình huống | Có thể kết luận gì? |
| --- | --- |
| `putLast(message)` hoàn tất bình thường, luồng khác lấy `message` ra | Có đường chuyển giao từ dữ liệu chuẩn bị trước lần thêm đến các hành động của bên nhận sau khi lấy |
| `offerLast(message)` trả `true`, bên nhận lấy phần tử | Việc thêm thành công vẫn dùng được để chuyển giao, dù không có chờ |
| `offerLast(message)` trả `false` | Phần tử chưa được thêm bởi lần gọi này; không có lần chuyển giao thành công đó |
| `pollFirst()` trả `null` | Không nhận được phần tử; không có dữ liệu phần tử để xử lý |
| `peekFirst()` nhận một phần tử | Có thể truy cập phần tử theo hợp đồng deque, nhưng không lấy khỏi deque và không tạo quyền sở hữu độc quyền |
| Chỉ gọi `size()` hoặc `isEmpty()` rồi đọc một biến dùng chung khác | Không dùng việc quan sát kích thước làm giao thức công bố tùy ý cho biến khác |

Hợp đồng nói đến cả truy cập và lấy phần tử, nhưng đối với một luồng xử lý công việc duy nhất, `takeFirst` hoặc `pollFirst` thành công thường biểu đạt chuyển giao rõ hơn `peekFirst`. Một luồng khác vẫn có thể lấy phần tử sau khi bạn `peek`.

Đừng viết “hàng đợi không rỗng nên tất cả dữ liệu dùng chung đã an toàn”. Lập luận cần bám vào chính đối tượng được chuyển và các lần ghi xảy ra trước việc công bố nó.

## 8. Kiểm tra tính đúng đắn mà không dựa vào may mắn

Một chương trình có tranh chấp dữ liệu có thể chạy hàng nghìn lần mà vẫn in ra kết quả mong muốn. Chạy lặp chỉ là quan sát thực nghiệm; nó không thay thế hợp đồng bộ nhớ.

Cách kiểm tra hữu ích hơn:

1. Xác định bên nào ghi từng trường.
2. Đánh dấu lần thêm thành công vào deque.
3. Đánh dấu lần bên nhận lấy hoặc truy cập phần tử.
4. Kiểm tra các lần đọc nằm sau điểm nhận.
5. Tìm mọi tham chiếu còn tồn tại và mọi lần sửa sau khi gửi.
6. Nếu có chiều phản hồi, tìm một đường đồng bộ riêng cho chiều đó.

`Thread.sleep()` không tạo quan hệ `happens-before` để công bố dữ liệu. Thêm thời gian chờ có thể làm lỗi khó xuất hiện hơn, nhưng không sửa được giao thức sai.

Các lệnh log cũng làm thay đổi nhịp thực thi. “Bật log thì hết lỗi” là lý do để kiểm tra lại đồng bộ, không phải bằng chứng chương trình đã đúng.

Việc dùng deque đúng bảo đảm công bố dữ liệu ở ranh giới chuyển giao. Nó không tự bảo đảm công việc hoàn thành đúng hạn, đúng thứ tự nghiệp vụ ở mọi cấu hình, hoặc chỉ được thực hiện đúng một lần sau các cơ chế thử lại. Đây là các thuộc tính khác cần thiết kế riêng.

## 9. Tự kiểm tra

1. **Có cần `volatile` cho mọi trường của một thông điệp được chuẩn bị xong, gửi qua deque và không sửa tiếp không?** Không chỉ vì mục đích công bố lần đầu này. Đường chuyển giao qua deque đã cung cấp quan hệ cần thiết.
2. **Bên gửi sửa mảng bên trong thông điệp sau khi `putLast` có an toàn chỉ nhờ deque không?** Không. Cần dừng sửa, sao chép dữ liệu hoặc phối hợp các lần truy cập về sau.
3. **`record Job(List<Item> items)` có mặc nhiên bất biến sâu không?** Không. Trường tham chiếu được cố định không có nghĩa danh sách và từng `Item` không thể đổi.
4. **Hai phần tử trong deque có thể cùng tham chiếu một đối tượng không?** Có. Hàng đợi không sao chép và không tự kiểm tra quyền sở hữu.
5. **Bên nhận đã tính xong một trường kết quả; bên gửi có thể đọc ngay nhờ lần gửi yêu cầu trước đó không?** Không tự động. Cần một đường bảo đảm cho chiều phản hồi, chẳng hạn gửi kết quả qua một deque khác.
6. **Không thấy kết quả sai khi chạy thử có đủ để chứng minh nhìn thấy dữ liệu đúng không?** Không. Cần chỉ ra chuỗi `happens-before` và không để các lần sửa cạnh tranh phá vỡ thiết kế.
