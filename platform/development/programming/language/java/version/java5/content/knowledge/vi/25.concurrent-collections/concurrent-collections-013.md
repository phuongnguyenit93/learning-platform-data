# Quan hệ công bố dữ liệu khi đưa phần tử vào collection đồng thời

Một luồng chuẩn bị cấu hình rồi đặt nó vào bản đồ dùng chung. Luồng khác tìm cấu hình và dùng các trường bên trong. Dù tham chiếu đã tới tay bên đọc, ta vẫn cần trả lời: **điều gì bảo đảm bên đọc nhìn thấy dữ liệu đã được chuẩn bị trước khi tham chiếu được công bố?**

Các collection đồng thời trong `java.util.concurrent` có hợp đồng bộ nhớ cho việc đưa đối tượng vào và truy cập đối tượng từ collection. Hợp đồng đó cho phép công bố an toàn (safe publication), nhưng không làm mọi đối tượng chứa bên trong tự trở thành an toàn khi sửa đồng thời.

## 1. Công bố tham chiếu và công bố trạng thái

Một đối tượng gồm tham chiếu và trạng thái: các trường số, chuỗi, mảng hoặc những đối tượng liên quan. Thiết kế chia sẻ dữ liệu đúng cần bảo đảm cả việc nhận được tham chiếu lẫn việc quan sát các phép ghi có liên quan.

Trong mô hình bộ nhớ Java (Java Memory Model, JMM), quan hệ **happens-before** cung cấp cơ sở để lập luận về khả năng nhìn thấy dữ liệu và thứ tự quan sát hợp lệ. Nó không chỉ là lời kể “luồng A chạy sớm hơn luồng B theo đồng hồ”. Định nghĩa và tính bắc cầu được nêu tại [JLS 17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

Ví dụ phân tích không an toàn:

```java
// Hai luồng cùng dùng một đối tượng chứa các trường thông thường này.
Config published;
boolean ready;

// Luồng ghi:
Config config = new Config();
config.endpoint = "https://example.invalid";
published = config;
ready = true;

// Luồng đọc:
if (ready) {
    use(published.endpoint);
}
```

Đoạn này chỉ minh họa cấu trúc lỗi, không phải chương trình độc lập. Nếu không có cơ chế đồng bộ hóa khác, cờ `ready` thông thường không tạo quan hệ công bố cần thiết. Không thể dùng việc “đã gán tham chiếu rồi” để kết luận trạng thái được đọc đúng.

`sleep`, `yield`, thời gian chờ dài hoặc việc máy hiện tại có nhiều lõi đều không thay thế cơ chế công bố.

## 2. Quy tắc của collection đồng thời

Hành động trong một luồng trước khi đưa đối tượng vào collection đồng thời happens-before hành động sau khi luồng khác truy cập hoặc lấy đối tượng đó từ collection. Quy tắc chung được ghi tại [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

Với bản đồ, cả khóa và giá trị có quy tắc công bố tương ứng; với hàng đợi hoặc danh sách, đối tượng được đưa vào là phần tử.

```text
Luồng ghi                                     Luồng đọc
1. Tạo Config
2. Ghi các trường và dữ liệu liên quan
3. configs.put("primary", config)  ────────►   4. config = configs.get("primary")
                                               5. Đọc trường của config

Nếu get trả đúng giá trị được công bố:
các phép ghi trước lần công bố happens-before các phép đọc sau khi nhận.
```

Điều kiện thiết kế trong sơ đồ là không có luồng khác tiếp tục sửa xung đột mà thiếu đồng bộ. Các giá trị đã chuẩn bị không cần mang `volatile` riêng chỉ để phục vụ lần bàn giao này.

`ConcurrentHashMap` diễn đạt cụ thể hơn: cập nhật trên một khóa có quan hệ happens-before với lần truy xuất khác `null` trên khóa đó khi lần truy xuất trả giá trị của cập nhật ấy. Xem [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Không dùng một lần `get` trả `null` hoặc phép kiểm tra kích thước như bằng chứng rằng một đối tượng khác đã được công bố. Lập luận phải đi qua lần truy cập nhận được dữ liệu có liên quan.

## 3. Chương trình chạy đầy đủ với ConcurrentHashMap

Lưu thành `CollectionPublicationDemo.java`. Các trường cố ý không `final`, không `volatile` để làm rõ vai trò của lần công bố qua bản đồ.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

public class CollectionPublicationDemo {
    static class Details {
        int retries;
    }

    static class Config {
        String endpoint;
        int[] ports;
        Details details;
    }

    static Config awaitConfig(ConcurrentMap<String, Config> configs)
            throws InterruptedException {
        long started = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(5);
        for (;;) {
            Config config = configs.get("primary");
            if (config != null) {
                return config;
            }
            if (System.nanoTime() - started >= budget) {
                throw new IllegalStateException("Publication not observed");
            }
            Thread.sleep(1); // Avoid a tight loop; not a publication mechanism.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentMap<String, Config> configs = new ConcurrentHashMap<>();

        Thread writer = new Thread(() -> {
            Config config = new Config();
            config.endpoint = "https://example.invalid";
            config.ports = new int[] {8080, 8443};
            config.details = new Details();
            config.details.retries = 3;
            configs.put("primary", config);
            // Do not mutate this config or its nested data after publication.
        }, "writer");

        writer.start();
        Config received = awaitConfig(configs);
        System.out.println("endpoint: " + received.endpoint);
        System.out.println("first port: " + received.ports[0]);
        System.out.println("retries: " + received.details.retries);
        writer.join();
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 CollectionPublicationDemo.java
java CollectionPublicationDemo
```

Stdout khi bên ghi chạy và giá trị được quan sát trước thời hạn kiểm tra:

```text
endpoint: https://example.invalid
first port: 8080
retries: 3
```

Nếu tiến trình bị ngắt bên ngoài, hoặc môi trường không cho bên ghi tiến triển đủ để vượt qua kiểm tra trong năm giây, chương trình có thể kết thúc bằng ngoại lệ thay vì stdout trên. Thời hạn chỉ giúp thí nghiệm không chờ vô hạn; nó không phải cam kết bộ lập lịch sẽ chạy một luồng trong năm giây.

### Vì sao các phép đọc được bảo đảm?

1. Bên ghi tự tạo `Config` sau khi luồng đó đã khởi chạy; luồng chính không có đường đọc trực tiếp tới đối tượng trước khi nó xuất hiện trong bản đồ.
2. `endpoint`, mảng `ports`, đối tượng `details` và `details.retries` đều được chuẩn bị trước `configs.put`.
3. Khi `get` trả khác `null`, bên đọc nhận giá trị từ lần công bố. Quan hệ happens-before nối các phép ghi trước đó tới các phép đọc sau này, gồm dữ liệu lồng nhau đã được chuẩn bị.
4. Sau `put`, bên ghi không sửa thêm đối tượng hoặc dữ liệu con; vì thế không có phép ghi cạnh tranh làm phá giả định đọc ổn định.
5. `writer.join()` ở sau các dòng in, nên nó không phải lý do những phép đọc trước đó đúng. `Thread.start()` cung cấp chiều từ bên khởi chạy tới luồng mới, không tự cung cấp chiều công bố dữ liệu mới tạo bên trong luồng ghi về luồng chính.

`Thread.sleep(1)` chỉ giảm việc quay vòng khi chưa có dữ liệu; nó không tạo quan hệ công bố. Trong ứng dụng thực tế, nếu cần chờ một kết quả hoặc một công việc, nên chọn cơ chế chờ phù hợp như `Future`, chốt đếm hoặc hàng đợi chặn thay vì tự xem bản đồ là kênh thông báo hoàn tất.

## 4. Phạm vi bao gồm những gì?

Quan hệ công bố không bị giới hạn ở giá trị tham chiếu gốc. Nếu bên ghi đã tạo mảng, điền phần tử và đặt mảng trong cấu hình trước khi công bố, bên đọc sau khi nhận cấu hình có cơ sở để đọc các phép ghi đó.

Nhưng không được áp dụng ngược khi dữ liệu đã sai trước lúc công bố. Ví dụ luồng A và B cùng sửa một mảng thiếu đồng bộ, rồi A đặt một đối tượng giữ mảng vào bản đồ: bản đồ không làm lịch sử tranh chấp trước đó trở thành đúng.

Nếu luồng B là bên chuẩn bị dữ liệu, A muốn công bố lại dữ liệu đó cho C, A cũng phải nhận dữ liệu từ B qua một quan hệ thích hợp:

```text
B chuẩn bị dữ liệu
  → B bàn giao an toàn cho A
  → A công bố vào collection đồng thời
  → C nhận và đọc
```

Tính bắc cầu giúp nối các quan hệ hợp lệ. Không được bỏ qua đoạn B → A chỉ vì đoạn A → C dùng collection đồng thời.

Đây là hợp đồng về hành vi quan sát được. Không cần giải thích bằng khẳng định máy móc rằng mỗi lần thêm đều “đẩy mọi cache về RAM”; JVM và phần cứng có nhiều cách hiện thực miễn tuân thủ JMM.

## 5. Công bố một lần không bảo vệ mọi lần sửa sau đó

Đoạn sau minh họa một lỗi khác:

```java
config.retries = 3;
map.put("primary", config);
config.retries = 5; // Bên đọc có thể đang truy cập cùng đối tượng.
```

Giả sử `Config` của đoạn minh họa có trường `retries` thông thường. Phép ghi 5 nằm sau lần công bố, nên không được bảo đảm bởi lần `put` trước đó. Nếu bên đọc cùng đọc trường này mà không có đồng bộ hóa bổ sung, có tranh chấp dữ liệu; không được hứa giá trị luôn là 3 hoặc luôn là 5.

Hai lựa chọn thường dễ kiểm soát:

- **Giá trị bất biến:** tạo hoàn chỉnh trước khi công bố rồi không sửa, bao gồm việc bảo vệ dữ liệu con có thể thay đổi.
- **Trạng thái có thể thay đổi nhưng có hợp đồng riêng:** khóa chung, trường `volatile`, kiểu nguyên tử hoặc một cơ chế phù hợp với các thao tác cần thực hiện.

`final` giúp thể hiện tính bất biến của trường và có quy tắc khởi tạo riêng khi đối tượng được xây dựng đúng, nhưng `final List<T>` không đóng băng nội dung danh sách. Các quy tắc trường `final` được mô tả tại [JLS 17.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.5).

Với cấu hình thường đọc và ít cập nhật, một cách thiết kế là tạo **đối tượng cấu hình mới** đầy đủ rồi thay giá trị bản đồ. Bên đang dùng phiên bản cũ tiếp tục dùng phiên bản cũ; bên truy xuất mới có thể nhận phiên bản mới. Không sửa trực tiếp một đối tượng mà các bên đọc đang coi là ổn định.

## 6. Không công bố this khi khởi tạo chưa hoàn tất

Ví dụ thiết kế nguy hiểm:

```java
class Config {
    int retries;

    Config(ConcurrentMap<String, Config> registry) {
        registry.put("primary", this);
        retries = 3; // Nằm sau lần công bố.
    }
}
```

Đây là đoạn minh họa cần import `ConcurrentMap`. Đối tượng thoát ra ngoài trong constructor trước khi việc chuẩn bị hoàn tất. Bên đọc có thể nhận tham chiếu trước phép gán `retries = 3`; collection không thể công bố trước một phép ghi chưa được thực hiện.

Nên hoàn tất constructor và mọi bước chuẩn bị cần thiết, sau đó mới đăng ký đối tượng từ bên ngoài. Việc tránh để `this` thoát sớm cũng quan trọng khi dựa vào các quy tắc khởi tạo trường `final`.

## 7. Không nhầm ba tầng bảo đảm

| Tầng | Điều được bảo đảm | Điều không tự có |
|---|---|---|
| Cấu trúc collection | Phương thức đúng hợp đồng khi truy cập đồng thời | Mọi chuỗi nhiều phương thức đều là giao dịch |
| Công bố dữ liệu | Quan hệ bộ nhớ cho dữ liệu chuẩn bị trước lần đưa vào, theo truy cập tương ứng | Bảo vệ mọi cập nhật sau khi công bố |
| Bất biến nghiệp vụ | Chỉ có nếu ứng dụng thiết kế đúng phạm vi cập nhật | Tự nguyên tử trên nhiều phần tử hay nhiều collection |

Ví dụ `ConcurrentMap<String, List<String>>` có thể công bố một danh sách đã điền dữ liệu an toàn. Nhưng sau đó nhiều luồng gọi `add` vào cùng một `ArrayList` vẫn không an toàn chỉ nhờ collection bên ngoài.

Hai khóa chứa hai nửa của cùng một phiên bản cấu hình cũng có thể bị đọc ở hai thời điểm khác nhau. Nếu cần một cặp trường nhất quán, cân nhắc gom chúng thành một giá trị bất biến được công bố cùng nhau hoặc dùng giao thức đọc/ghi có phối hợp.

Thao tác duyệt cũng có hợp đồng riêng. Iterator ảnh chụp có thể giữ tham chiếu tới một phiên bản cấu trúc cũ; iterator yếu nhất quán có thể phản ánh một số cập nhật. Bảo đảm công bố của các phần tử được nhận không có nghĩa cả lượt duyệt là một ảnh chụp giao dịch của toàn trạng thái.

## 8. Collection cũng cần được chia sẻ đúng cách

Các bảo đảm nói trên áp dụng khi các luồng thật sự truy cập cùng đối tượng collection bằng một đường chia sẻ hợp lệ. Đặt collection trong một trường rồi thay tham chiếu trường đó tùy ý giữa các luồng vẫn tạo ra một bài toán công bố khác.

Các mẫu thường dùng gồm:

- Tạo collection trước `Thread.start()` rồi truyền cho các luồng, như ví dụ.
- Giữ collection trong một trường `final` của đối tượng được xây dựng và công bố đúng cách.
- Công bố tham chiếu thông qua một cơ chế đồng bộ hóa thích hợp nếu cần thay collection hiện hành.

Ngoài ra, `ConcurrentHashMap` không tự chia sẻ dữ liệu giữa các tiến trình hoặc máy khác nhau. Quan hệ bộ nhớ của JVM không thay thế giao thức truyền thông và lưu trữ ngoài tiến trình.

## 9. Cách lập luận một lần công bố

Với mỗi lần đọc trạng thái dùng chung, hãy xác định:

1. Phép ghi nào cần được quan sát và luồng nào thực hiện nó.
2. Các phép ghi đó có hoàn tất trước lần công bố không.
3. Lần truy cập nào của bên đọc nhận được đối tượng hoặc giá trị tương ứng.
4. Sau khi nhận, còn bên nào sửa đối tượng hoặc đối tượng con thiếu phối hợp không.
5. Bên đọc cần một giá trị riêng lẻ hay một bất biến trải qua nhiều giá trị.

Chạy ví dụ đúng nhiều lần là kiểm chứng hữu ích, nhưng không chứng minh một thiết kế thiếu happens-before sẽ luôn đúng. Chứng minh phải dựa vào quan hệ giữa các thao tác và hợp đồng API.

## 10. Tự kiểm tra

1. Trường thường được gán trước `put`, đọc sau `get` nhận giá trị và không còn phép sửa cạnh tranh: cần thêm `volatile` chỉ để công bố lần đó không? — Không.
2. Sửa mảng sau lần đưa vào collection có tự an toàn không? — Không.
3. `get` trả `null` có chứng minh một dữ liệu khác đã sẵn sàng không? — Không.
4. Vì sao đưa `this` vào registry quá sớm nguy hiểm? — Bên khác có thể đọc trước khi việc khởi tạo cần thiết hoàn tất.
5. Collection đồng thời có làm một lượt đọc nhiều khóa thành một phiên bản nhất quán không? — Không; cần thiết kế phạm vi trạng thái phù hợp.
