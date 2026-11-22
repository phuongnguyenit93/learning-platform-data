# Công bố đối tượng an toàn bằng các cơ chế đồng bộ

## Khái niệm: chuyển tham chiếu chưa đủ để chuyển trạng thái đúng cách

**Công bố đối tượng (publication)** là làm cho một đối tượng có thể được mã khác hoặc luồng khác tiếp cận, chẳng hạn bằng cách:

- Gán tham chiếu vào một field dùng chung.
- Đưa đối tượng vào hàng đợi.
- Trả đối tượng qua kết quả của một tác vụ.
- Cung cấp một đối tượng dùng chung từ khởi tạo lớp.

**Công bố an toàn (safe publication)** đòi hỏi một cơ chế phù hợp để luồng nhận có thể quan sát trạng thái đã được chuẩn bị trước khi công bố, thay vì chỉ tình cờ thấy một tham chiếu khác `null`.

Điểm mấu chốt là quan hệ **happens-before** trong Mô hình bộ nhớ Java (Java Memory Model, JMM): các thao tác ghi trạng thái cần xảy ra-trước các thao tác đọc tương ứng của bên nhận.

Một phép gán tham chiếu riêng lẻ không tự trở thành toàn bộ giao thức chuyển giao giữa các luồng.

Bài dùng các cơ chế hiện hành và ví dụ chạy trên JDK 17 trở lên.

## Vì sao cần công bố an toàn?

Giả sử:

```java
// Mảnh minh họa, không phải chương trình thử nghiệm đầy đủ:
class Data {
    int answer;

    Data() {
        answer = 42;
    }
}

Data shared;
```

Một luồng thực hiện `shared = new Data();`, còn luồng khác đọc field thường `shared` mà không có quan hệ đồng bộ hóa thích hợp.

Chỉ nhìn thứ tự trong mã của luồng ghi không đủ để kết luận luồng đọc chắc chắn thấy một trạng thái đã khởi tạo đầy đủ. Luồng đọc cũng không được bảo đảm sẽ quan sát việc thay tham chiếu vào một thời điểm mà ứng dụng mong đợi.

Với dữ liệu thường không được bảo vệ đúng, việc bên đọc thấy tham chiếu khác null chưa đủ chứng minh mọi field liên quan sẽ có giá trị sau constructor theo suy luận tuần tự đơn giản.

Thêm `sleep`, chờ lâu hơn hoặc thử trên một máy nhiều lần không tạo một đường happens-before.

Cơ sở của lập luận nằm tại [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5).

## Ba trách nhiệm cần tách rõ

| Trách nhiệm | Câu hỏi |
| --- | --- |
| Xây dựng đối tượng | Trạng thái cần chia sẻ đã được hoàn tất chưa? |
| Công bố ban đầu | Luồng nhận đi qua cơ chế nào để thấy những ghi trước công bố? |
| Sử dụng sau công bố | Đối tượng còn bị sửa không, và các thay đổi đó được bảo vệ ra sao? |

Công bố an toàn không tự biến một đối tượng có thể thay đổi thành đối tượng an toàn luồng cho mọi thao tác về sau.

Ví dụ, đưa một đối tượng vào hàng đợi có thể công bố các ghi trước đó. Nếu bên gửi tiếp tục sửa cùng đối tượng sau khi đưa vào, các lần sửa mới cần được xét theo giao thức riêng.

Một thiết kế dễ lý giải là tạo dữ liệu hoàn chỉnh, công bố nó, rồi không sửa dữ liệu đã công bố. Nếu cần cập nhật, có thể công bố một ảnh chụp mới theo cơ chế phù hợp.

## Bản đồ các cơ chế công bố

| Cơ chế | Điểm nối bộ nhớ cần dựa vào |
| --- | --- |
| Khởi tạo lớp | Hoàn tất khởi tạo lớp và quy tắc đồng bộ hóa của JVM |
| Field volatile | Ghi tham chiếu/tín hiệu volatile và đọc phù hợp ở phía nhận |
| Khóa | Nhả rồi lấy lại cùng monitor theo quan hệ đồng bộ hóa |
| BlockingQueue | Thao tác trước khi đưa phần tử vào và phía khác lấy/truy cập phần tử |
| ExecutorService và Future | Gửi tác vụ, hành động của tác vụ và nhận kết quả qua get |
| Thread.start / Thread.join | Hành động trước start đi vào luồng mới; hành động của luồng kết thúc đi tới phía join thành công |

Không cần tự tạo một cờ rồi chờ bận nếu một hàng đợi hoặc cơ chế kết quả tác vụ đã biểu đạt đúng bài toán.

Mỗi cơ chế chỉ có hiệu lực khi bên gửi và bên nhận thực sự dùng đúng điểm nối. Viết một thao tác synchronized ở một phía nhưng đọc trực tiếp field từ phía khác không tự tạo một giao thức có khóa đầy đủ.

## 1. Công bố qua khởi tạo lớp

Dạng thường gặp:

```java
static final class Holder {
    static final Message INSTANCE = new Message();
}
```

Đây là mảnh khai báo trong một lớp bao có kiểu `Message`; chương trình hoàn chỉnh sẽ dùng chính cấu trúc này.

JVM điều phối quá trình khởi tạo lớp. Một luồng truy cập kết quả khởi tạo lớp theo quy tắc ngôn ngữ được hưởng bảo đảm của quá trình khởi tạo đó.

Trong mẫu holder, đối tượng được tạo trong quá trình khởi tạo `Holder`, rồi được truy cập qua `Holder.INSTANCE`.

Hai điểm cần giữ:

- Tính đúng không chỉ nằm ở việc tham chiếu mang từ khóa `final`; quy trình khởi tạo lớp mới là phần quan trọng của cơ chế công bố này.
- Nếu đối tượng được tham chiếu vẫn có các thao tác sửa về sau, static final không tự bảo vệ các thao tác đó.

`static final List<...>`, chẳng hạn, chỉ giữ ràng buộc của tham chiếu. Nó không tự làm collection sâu bên trong trở thành bất biến.

Xem quy trình tại [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.2).

## 2. Công bố qua tham chiếu volatile

Mảnh minh họa:

```java
// Các thành viên của một lớp có kiểu Message:
private volatile Message current;

void publish() {
    Message prepared = new Message();
    current = prepared;
}

Message read() {
    return current;
}
```

Trong `publish`, đối tượng được xây dựng trước rồi mới ghi tham chiếu vào field volatile. Bên nhận đọc field đó để nhận đối tượng đã công bố.

Một cách sử dụng có chủ đích:

```java
// Mảnh minh họa trong một phương thức:
Message snapshot = current;
if (snapshot != null) {
    System.out.println(snapshot.describe());
}
```

Lấy tham chiếu một lần vào biến cục bộ giúp các lần sử dụng sau đó cùng làm việc với một đối tượng. Nếu luồng ghi có thể thay `current`, đọc field này nhiều lần có thể nhận các phiên bản khác nhau.

Nếu bên đọc chạy trước lần công bố, `snapshot` có thể là null. Volatile không làm đối tượng được tạo sớm hơn và không thay cho việc chờ điều kiện sẵn sàng nếu ứng dụng cần chờ.

Ngoài ra, `current` là volatile không có nghĩa mọi field trong `Message` trở thành volatile. Bảo đảm áp dụng cho các ghi trước khi công bố qua giao thức này; các cập nhật tiếp theo cần được phân tích riêng.

## 3. Công bố bằng cùng một khóa

Ví dụ một nơi lưu trữ nhỏ, đặt bên trong lớp có kiểu `Message`:

```java
static final class Registry {
    private final Object lock = new Object();
    private Message current;

    void publish(Message message) {
        synchronized (lock) {
            current = message;
        }
    }

    Message read() {
        synchronized (lock) {
            return current;
        }
    }
}
```

Điểm quan trọng là cả hai phía dùng **cùng một đối tượng lock**. Các thao tác chuẩn bị đối tượng trước lúc nhả khóa có thể được phía đọc sau đó tiếp nhận qua quan hệ nhả/lấy khóa phù hợp.

Nếu `read` chạy trước `publish`, nó vẫn có thể trả null. Khóa giữ tính đúng của các quan hệ truy cập; nó không tự ép mọi lời gọi đọc phải đợi tới khi có dữ liệu.

Ví dụ này giả sử sau khi Message được công bố thì không bị sửa. Nếu vẫn cần sửa, việc trả một tham chiếu ra ngoài khóa không tự làm mọi phép đọc tiếp theo của đối tượng đó nằm trong vùng khóa.

Không đổi khóa thành hai đối tượng khác nhau ở hai phía. Tên biến giống nhau hoặc hai khối đều có chữ synchronized không đủ; cần đúng cùng monitor theo giao thức.

## 4. Công bố bằng BlockingQueue

Một hàng đợi chặn biểu diễn tự nhiên mô hình bên tạo dữ liệu và bên nhận dữ liệu.

Hợp đồng của `BlockingQueue` cung cấp quan hệ bộ nhớ từ các hành động trước khi đưa một phần tử vào hàng đợi đến các hành động sau khi luồng khác truy cập hoặc lấy phần tử tương ứng.

Vì vậy:

```text
Hoan tat Message
      |
      v
put(message)
      |
      | chuyen giao qua hang doi
      v
take() nhan message
      |
      v
Doc trang thai da cong bo
```

Bên nhận không cần tự quay vòng đọc một field thường để chờ tham chiếu xuất hiện. Nó có thể dùng `take()` để chờ phần tử theo hợp đồng của hàng đợi.

Hàng đợi không tạo bản sao đối tượng. Nếu bên gửi giữ một bí danh tham chiếu và tiếp tục sửa đối tượng, các bên vẫn đang dùng chung một đối tượng. Công bố an toàn và chuyển quyền sở hữu là hai quyết định cần được thiết kế rõ.

Xem [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 5. Công bố qua ExecutorService và Future.get

Với một tác vụ được gửi bằng `ExecutorService`:

- Các hành động trước khi gửi tác vụ xảy ra-trước hành động của tác vụ theo hợp đồng API.
- Hành động của tác vụ xảy ra-trước việc nhận kết quả theo quan hệ được `Future.get()` cung cấp.

Do đó, có thể tạo một đối tượng trong tác vụ rồi nhận nó qua `get`, thay vì để tác vụ tự ghi vào một field thường mà phía nhận đọc tùy ý.

```java
// Mảnh minh họa trong phương thức có xử lý ngoại lệ phù hợp:
Future<Message> future = executor.submit(Message::new);
Message message = future.get();
```

`get()` cũng biểu đạt việc chờ hoàn tất và cơ chế báo lỗi tác vụ. Công bố dữ liệu không đồng nghĩa mọi tác vụ đều thành công; bên gọi vẫn phải xử lý hoặc truyền các ngoại lệ theo hợp đồng.

Xem [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) và [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html).

Không suy luận rằng mọi cách kiểm tra trạng thái của mọi đối tượng tác vụ đều hoàn toàn tương đương `Future.get()`. Khi chọn API khác, hãy dùng đúng bảo đảm mà API đó nêu.

## Chương trình đầy đủ: ba cơ chế chuyển giao

Lưu thành `SafePublicationDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SafePublicationDemo {
    static final class Message {
        private int number;
        private String text;

        Message() {
            number = 42;
            text = "ready";
        }

        String describe() {
            return number + ":" + text;
        }
    }

    static final class Holder {
        static final Message INSTANCE = new Message();
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        Thread holderReader = new Thread(() ->
                System.out.println("holder=" + Holder.INSTANCE.describe()));
        holderReader.start();
        holderReader.join();

        BlockingQueue<Message> channel = new ArrayBlockingQueue<>(1);
        Thread queueReader = new Thread(() -> {
            try {
                Message message = channel.take();
                System.out.println("queue=" + message.describe());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        });
        queueReader.start();
        channel.put(new Message());
        queueReader.join();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Message> future = executor.submit(Message::new);
            Message message = future.get();
            System.out.println("future=" + message.describe());
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 SafePublicationDemo.java
java SafePublicationDemo
```

Kết quả:

```text
holder=42:ready
queue=42:ready
future=42:ready
```

## Phân tích ví dụ

### Vì sao các field dữ liệu cố ý không phải final?

`Message.number` và `Message.text` là field thường, được ghi trong constructor.

Ví dụ làm vậy để quan sát vai trò của từng cơ chế công bố đối với dữ liệu thường, không dựa riêng vào ngữ nghĩa đặc biệt của final field.

Sau khi constructor kết thúc, chương trình không sửa các field đó nữa. `Message` không cung cấp setter và không làm lộ `this` trong khi xây dựng.

Trong mã thiết kế đối tượng bất biến thực tế, nên sử dụng final và các biện pháp bất biến phù hợp thay vì cố ý để field thường chỉ vì ví dụ đã công bố an toàn.

Từ khóa final trên **lớp** `Message` ngăn kế thừa lớp; nó không tự biến hai field thường của Message thành final.

### Nhánh holder

Luồng `holderReader` truy cập `Holder.INSTANCE`. Đối tượng được tạo và gắn vào static field trong quá trình khởi tạo Holder.

Lời gọi `join` sau đó giúp main đợi lượt quan sát hoàn tất trước khi tiếp tục phần kế tiếp, nên ba dòng output có thứ tự rõ ràng.

### Nhánh queue

Luồng nhận được khởi động trước, rồi main mới tạo Message và đưa vào hàng đợi. Vì thế không thể giải thích việc công bố Message này chỉ bằng “đối tượng đã được tạo trước Thread.start”.

Điểm nối cho trạng thái của Message trong nhánh này là `put` và `take` của hàng đợi.

Nếu luồng nhận đang chờ và bị interrupt, nó khôi phục cờ interrupt rồi báo lỗi trong ví dụ. Lượt chạy bình thường không tạo interruption, nên in đầy đủ dữ liệu đã được chuyển qua hàng đợi.

### Nhánh future

Tác vụ chạy ở executor tạo một Message mới. Main nhận kết quả qua `future.get()` rồi mới gọi `describe()`.

`finally` gọi `shutdown()` để executor không giữ tài nguyên sau khi ví dụ đã hoàn thành việc sử dụng. Việc shutdown không phải thao tác công bố kết quả; `get()` đã đảm nhiệm quan hệ nhận kết quả trong giao thức này.

## Thread.start và Thread.join tạo quan hệ theo hai hướng khác nhau

Nếu một đối tượng được chuẩn bị trước khi gọi `thread.start()`, các hành động trước start được liên kết tới các hành động trong luồng mới theo JMM.

Hướng này là:

```text
Luong tao: chuan bi du lieu -> start
                                  |
                                  v
                            Luong moi doc
```

Ngược lại, khi một luồng hoàn tất và một luồng khác đã phát hiện việc hoàn tất bằng `join` thích hợp, các hành động của luồng đã kết thúc được liên kết tới phía tiếp tục sau join.

Hai bảo đảm không có nghĩa mọi cập nhật trong tương lai giữa hai luồng đều tự đồng bộ. Nếu sau start các luồng tiếp tục dùng chung dữ liệu có thể thay đổi, vẫn cần cơ chế phù hợp.

Với `join` có hạn chờ, phải phân biệt việc đã xác nhận luồng kết thúc với việc chỉ hết thời gian chờ. Không coi “đã gọi một hàm join nào đó” là bằng chứng tác vụ đã hoàn tất.

Trong bài, mọi lời gọi join đều dùng để chờ luồng ví dụ kết thúc, không tạo một giao thức quay vòng cho dữ liệu thay đổi liên tục.

## Final field có bảo đảm riêng nhưng không thay thế mọi cơ chế công bố

Một đối tượng được xây dựng đúng cách, không làm tham chiếu `this` thoát ra trong constructor, có bảo đảm đặc biệt về các final field theo JMM.

Điều này rất quan trọng với thiết kế bất biến. Tuy nhiên, không nên rút gọn thành “chỉ cần một final field là mọi field trong mọi đối tượng liên quan đều an toàn”.

Cần giữ rõ:

- Final field có ngữ nghĩa riêng.
- Field thường có thể cần quan hệ happens-before thích hợp.
- Tham chiếu final không tự làm đối tượng được tham chiếu bất biến.
- Việc sửa đối tượng sau xây dựng không được tự bao phủ bởi bảo đảm ban đầu.

Bài tập trung vào công bố qua cơ chế đồng bộ hóa để có đường giải thích rõ cho toàn bộ trạng thái đã chuẩn bị. Ngữ nghĩa chi tiết của final field nằm tại [JLS §17.5](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.5).

## Tránh để this thoát ra trước khi hoàn tất xây dựng

Một đối tượng có thể bị công bố quá sớm nếu constructor:

- Ghi `this` vào một nơi dùng chung.
- Đăng ký một callback có thể được gọi ngay từ luồng khác.
- Khởi động một luồng dùng chính đối tượng trước khi trạng thái cần thiết hoàn tất.
- Gọi mã bên ngoài có thể giữ lại tham chiếu tới đối tượng đang xây dựng.

Nếu luồng khác truy cập giữa quá trình xây dựng, một cơ chế dùng về sau không tự sửa lại những gì đã bị quan sát quá sớm.

Một cách tổ chức dễ kiểm soát là:

1. Hoàn thành constructor.
2. Hoàn tất các bước chuẩn bị thuộc hợp đồng đối tượng.
3. Sau đó mới đăng ký, khởi động hoặc công bố bằng cơ chế đã chọn.

Không phải mọi việc đăng ký callback đều lập tức gây lỗi, nhưng phải biết callback có thể được gọi khi nào và có làm lộ đối tượng cho nơi khác trước thời điểm an toàn hay không.

## Công bố an toàn không đồng nghĩa sở hữu duy nhất hoặc an toàn cho mọi cập nhật

Sau khi một Message đi qua hàng đợi:

- Bên nhận có thể đọc trạng thái trước công bố đúng cách.
- Bên gửi có thể vẫn giữ tham chiếu đến cùng Message.
- Nếu cả hai cùng sửa, cần quy tắc mới.

Các lựa chọn thiết kế phổ biến:

| Mô hình | Điều cần giữ |
| --- | --- |
| Bất biến sau công bố | Không sửa trạng thái được chia sẻ; bảo vệ nội dung tham chiếu sâu |
| Chuyển quyền sở hữu | Bên gửi không tiếp tục dùng đối tượng như dữ liệu có thể thay đổi của mình |
| Trạng thái có khóa | Mọi truy cập liên quan giữ cùng giao thức khóa |
| Ảnh chụp được thay thế | Tạo trạng thái mới rồi công bố; phía đọc dùng một ảnh chụp nhất quán |
| Cấu trúc đồng thời | Dùng đúng thao tác ghép do API cung cấp |

Một collection an toàn luồng không tự bảo vệ từng đối tượng phần tử có thể thay đổi. Một field volatile chứa tham chiếu cũng không tự khóa mọi phương thức của đối tượng được trỏ tới.

## Quy trình tự kiểm tra một thiết kế công bố

1. Liệt kê các field cần được hoàn tất trước khi bên nhận sử dụng.
2. Xác định lúc nào tham chiếu bắt đầu có thể được luồng khác tiếp cận.
3. Chỉ rõ thao tác công bố: gán volatile, nhả khóa, put, kết quả tác vụ hoặc khởi tạo lớp.
4. Chỉ rõ thao tác tiếp nhận tương ứng.
5. Vẽ đường happens-before từ ghi trạng thái đến đọc trạng thái.
6. Xem có cập nhật nào sau công bố hoặc đường truy cập nào đi ngoài giao thức không.
7. Xác định yêu cầu chờ, hủy và báo lỗi độc lập với yêu cầu bộ nhớ.

Nếu không vẽ được điểm tiếp nhận, đừng thay bằng lý do “đã chờ đủ lâu” hoặc “tham chiếu được gán nguyên tử”.

Tính nguyên tử của một phép gán tham chiếu và khả năng quan sát trạng thái đối tượng là hai phần khác nhau của lập luận.

## Lỗi phổ biến và cách phát hiện

| Hiểu nhầm | Điều cần kiểm tra |
| --- | --- |
| Tham chiếu khác null là đối tượng đã công bố an toàn | Cơ chế tạo quan hệ với các ghi trong constructor là gì? |
| Chỉ bên ghi synchronized là đủ | Bên đọc có dùng cùng khóa không? |
| Gán volatile sau khi đã làm lộ this là sửa được mọi thứ | Có quan sát sớm nào đã xảy ra không? |
| Hàng đợi sao chép dữ liệu cho bên nhận | Hai phía có đang giữ cùng tham chiếu không? |
| Future hoàn tất thì mọi thao tác đọc tùy ý đều tương đương get | API nào cung cấp bảo đảm nhận kết quả đang dùng? |
| Static final làm mọi dữ liệu sâu bất biến | Đối tượng và nội dung tham chiếu có còn thay đổi không? |
| Công bố ban đầu đúng là mọi cập nhật sau cũng đúng | Giao thức cho lần sửa mới là gì? |
| Test nhiều lần ra đúng là thay cho JMM | Đường happens-before cụ thể nằm ở đâu? |

## Thực hành kiểm chứng

1. Chạy chương trình và gắn mỗi dòng output với đúng cơ chế công bố.
2. Vẽ đường từ constructor Message đến `describe()` trong nhánh queue; giải thích vì sao Thread.start không phải điểm công bố Message đó.
3. Chuyển nhánh future sang tạo Message trước submit rồi để tác vụ đọc nó; xác định bảo đảm theo hướng gửi tác vụ.
4. Viết một nơi lưu Message dùng volatile và lấy một bản tham chiếu cục bộ trước khi đọc các field.
5. Viết một nơi lưu dùng khóa chung, rồi chỉ ra vì sao một hàm đọc bỏ khóa làm mất lập luận đang có.
6. Thêm một thao tác sửa sau công bố vào bản thử nghiệm và xác định rõ cơ chế còn thiếu trước khi chạy; không yêu cầu lỗi phải tái hiện trong từng lượt.

Điều cần nắm là **hoàn tất trạng thái, công bố qua một cơ chế có bảo đảm và tiếp nhận đúng cơ chế ấy**. Sau đó, mọi thay đổi mới vẫn phải tuân theo mô hình chia sẻ mà thiết kế lựa chọn.
