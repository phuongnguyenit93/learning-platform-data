# Quan sát thời gian phân giải và ngoại lệ mà không suy diễn mọi lần gọi đều tạo truy vấn DNS

## Mục tiêu bài học

Trong mô-đun **JAVA_VERSION_JAVA18**, chúng ta tìm hiểu những điểm của Java 18 vẫn có giá trị trên JDK hiện đại và cách kiểm chứng hợp đồng của các API như `InetAddress`. Bài này thuộc chương **Hợp đồng InetAddress**: đo thời gian một lời gọi phân giải tên, ghi nhận kết quả hoặc ngoại lệ, rồi diễn giải số liệu đúng với điều thực sự quan sát được.

Sau bài học, bạn có thể:

- Đo thời gian thực thi `InetAddress.getAllByName(String)` bằng `System.nanoTime()` và tách thời gian đo khỏi thời gian in log.
- Phân biệt **lời gọi API phân giải tên**, **hoạt động của bộ phân giải** và **gói truy vấn DNS thực sự đi trên mạng**.
- Ghi nhận `UnknownHostException` mà không kết luận vội rằng DNS đã trả về NXDOMAIN, đã hết thời gian chờ hoặc đã phát sinh truy vấn mới.
- Giải thích vai trò của địa chỉ IP dạng literal, tệp hosts, cache, bộ phân giải hệ điều hành và `InetAddressResolverProvider` trên JDK hỗ trợ SPI.
- Thiết kế thí nghiệm có giới hạn kết luận rõ ràng, phù hợp với API còn được hỗ trợ trên JDK hiện nay.

## 1. Chính xác thì đang quan sát điều gì?

Đoạn lệnh:

```java
InetAddress[] addresses = InetAddress.getAllByName("example.com");
```

yêu cầu Java trả về các địa chỉ IP ứng với tên được truyền vào, hoặc ném `UnknownHostException` nếu không thể xác định địa chỉ theo cơ chế phân giải đang cấu hình. Tuy nhiên, **lời gọi API không đồng nhất với một truy vấn DNS trên mạng**.

Một lời gọi có thể đi qua các tầng sau; thứ tự và sự hiện diện của từng tầng tùy JDK, hệ điều hành và cấu hình:

```text
Ứng dụng Java
    |
    v
InetAddress.getAllByName(host)
    |
    +--> Xử lý địa chỉ IP dạng literal (nếu đầu vào phù hợp)
    |
    +--> Cache phân giải trong JVM (nếu có kết quả dùng được)
    |
    v
Bộ phân giải được JVM sử dụng
    |    (mặc định hoặc nhà cung cấp InetAddressResolverProvider)
    |
    +--> Cấu hình tên cục bộ, tệp hosts, cache hệ điều hành, ...
    |
    +--> Truy vấn DNS trên mạng (chỉ khi cần và được cấu hình)
    v
Địa chỉ / lỗi phân giải
```

Sơ đồ thể hiện **những khả năng**, không khẳng định mọi máy hay mọi lần gọi đều đi qua toàn bộ các nhánh. Đặc biệt:

| Thao tác | Điều có thể quan sát | Điều không thể tự suy ra |
| --- | --- | --- |
| `getAllByName("127.0.0.1")` | Nhận địa chỉ IP từ biểu diễn số | Đã gửi truy vấn DNS |
| `getAllByName("localhost")` | Nhận một hoặc nhiều địa chỉ theo cấu hình máy | Chắc chắn có truy vấn ra máy chủ DNS |
| `getAllByName("example.com")` | Trả địa chỉ hoặc ném `UnknownHostException` | Mỗi lần gọi ứng với đúng một gói DNS |
| Gọi lại cùng tên | Thời gian và kết quả có thể khác lần trước | Chắc chắn lần đầu không cache hoặc lần sau có cache |
| `address.getHostAddress()` | Chuỗi IP dạng số | Đã thực hiện phân giải tên ngược |
| `address.getHostName()` / `getCanonicalHostName()` | Tên hoặc biểu diễn thay thế tùy thông tin và khả năng phân giải | Mọi lần gọi đều thực hiện một truy vấn reverse DNS mới |

**Chú ý:** `getHostName()` có thể tận dụng tên đã gắn với đối tượng; `getCanonicalHostName()` có thể cần thêm bước phân giải tên. Vì thế khi muốn đo riêng lời gọi `getAllByName`, hãy định thời **ngay quanh lời gọi đó**, trước khi tạo chuỗi hiển thị, ghi log hoặc gọi những phương thức có thể liên quan tới phân giải tên khác.

## 2. Chương trình đo thời gian và ghi nhận ngoại lệ

Chương trình sau chỉ sử dụng API Java chuẩn còn được hỗ trợ trên JDK hiện đại. Nó thử ba lần cho mỗi đầu vào để minh họa sự biến thiên, đồng thời in địa chỉ IP ở dạng số nhằm tránh đưa thao tác lấy tên ngược vào phép đo.

Lưu thành `ObserveInetAddress.java`:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.StringJoiner;

public class ObserveInetAddress {
    private static void lookup(String host, int attempt) {
        long started = System.nanoTime();

        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            long elapsedNanos = System.nanoTime() - started;

            // Tạo thông điệp sau khi đã chốt thời gian của lời gọi API.
            StringJoiner numericAddresses = new StringJoiner(", ");
            for (InetAddress address : addresses) {
                numericAddresses.add(address.getHostAddress());
            }

            System.out.printf(
                    "host=%s attempt=%d result=OK elapsed=%.3f ms addresses=[%s]%n",
                    host, attempt, elapsedNanos / 1_000_000.0, numericAddresses);
        } catch (UnknownHostException e) {
            long elapsedNanos = System.nanoTime() - started;

            System.out.printf(
                    "host=%s attempt=%d result=UnknownHostException "
                            + "elapsed=%.3f ms message=%s%n",
                    host, attempt, elapsedNanos / 1_000_000.0, e.getMessage());
        }
    }

    public static void main(String[] args) {
        String[] hosts = args.length == 0
                ? new String[] {"localhost", "127.0.0.1", "missing-host.invalid"}
                : args;

        for (String host : hosts) {
            for (int attempt = 1; attempt <= 3; attempt++) {
                lookup(host, attempt);
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 18 hoặc JDK mới hơn:

```bash
javac ObserveInetAddress.java
java ObserveInetAddress

# Có thể tự chỉ định các tên thuộc môi trường thử nghiệm.
java ObserveInetAddress localhost 127.0.0.1
```

`missing-host.invalid` sử dụng miền cấp cao nhất `.invalid` dành cho các ví dụ không hợp lệ. Nó giúp minh họa nhánh ngoại lệ, **nhưng không bảo đảm** một môi trường cụ thể sẽ thất bại hoặc phát sinh lưu lượng DNS: cấu hình hosts, resolver tùy biến hay hệ thống mạng có thể làm thay đổi kết quả. Không dùng chương trình để sinh hàng loạt tên ngẫu nhiên và tạo tải lên hạ tầng phân giải thực tế.

Điểm chính của cách đo:

1. `System.nanoTime()` cung cấp giá trị thích hợp để tính **khoảng thời gian đã trôi qua** bằng phép trừ; không dùng giá trị đơn lẻ như một mốc thời gian tuyệt đối.
2. `elapsedNanos` được ghi lại ngay khi `getAllByName` trả về hoặc ném `UnknownHostException`; thao tác nối chuỗi và `printf` nằm ngoài khoảng đo.
3. Mỗi dòng ghi rõ tên đầu vào, số lần thử, kết quả, thời gian tính bằng mili giây và địa chỉ dạng số (nếu có).
4. Chương trình **không** tự xác nhận đã có truy vấn DNS, cache hit, TTL nào đang có hiệu lực, hay máy chủ DNS nào trả lời.

Các địa chỉ trả về, thứ tự IPv4/IPv6 và thời gian thực tế phụ thuộc môi trường. Ngay cả `localhost` cũng không nhất thiết luôn cho ra cùng một danh sách trên mọi máy.

## 3. Diễn giải `UnknownHostException` cho đúng

`UnknownHostException` là tín hiệu từ API rằng địa chỉ cho đầu vào đó không được xác định thành công theo cơ chế phân giải đang dùng. **Tên ngoại lệ không phải bằng chứng cho một nguyên nhân mạng duy nhất.**

Ví dụ, ngoại lệ có thể liên quan đến:

- Tên không có bản ghi thích hợp theo bộ phân giải và cấu hình hiện hành.
- Lỗi hoặc sự cố trong đường phân giải tên (cấu hình, máy chủ, mạng hoặc nhà cung cấp resolver).
- Kết quả thất bại đã được cache, khiến lần gọi sau cũng thất bại mà không cần thực hiện lại truy vấn bên ngoài.
- Đầu vào dạng địa chỉ số không hợp lệ; một số phương thức tạo địa chỉ từ byte cũng ném `UnknownHostException` khi độ dài mảng địa chỉ không hợp lệ, dù không cần DNS.

Từ một lần bắt được ngoại lệ, **không đủ căn cứ** để khẳng định:

- Máy chủ DNS trả mã `NXDOMAIN`.
- Truy vấn DNS bị timeout hoặc không có phản hồi.
- JVM vừa gửi gói DNS mới.
- Tên đó không thể phân giải được trong mọi mạng hoặc tại mọi thời điểm.

Cũng cần tách lỗi phân giải tên khỏi lỗi **kết nối**. `UnknownHostException` khi gọi `getAllByName` khác với `ConnectException` hoặc `SocketTimeoutException` có thể xuất hiện khi một chương trình tiếp tục mở socket tới một địa chỉ đã biết. Để học về thời gian phân giải, ví dụ chỉ đo `getAllByName`, không gộp thêm `Socket.connect` vào cùng kết quả.

Nếu cần điều tra sâu hơn, hãy giữ lại loại ngoại lệ, thông điệp, đầu vào, thời điểm chạy, phiên bản JDK và môi trường mạng. Thông điệp ngoại lệ phục vụ chẩn đoán; không nên viết logic phụ thuộc vào văn bản thông điệp vì nó có thể khác giữa các bộ phân giải.

## 4. Vì sao các lần đo có thể nhanh, chậm hoặc giống nhau?

Khi lặp lại cùng một hostname trong một tiến trình JVM, có nhiều yếu tố tác động:

| Yếu tố | Tác động có thể thấy | Giới hạn kết luận |
| --- | --- | --- |
| Địa chỉ dạng literal | Phân tích địa chỉ số thường không cần DNS | Một phép đo nhanh không chứng minh điều gì về tốc độ máy chủ DNS |
| Tệp hosts và tên cục bộ | Tên có thể được trả kết quả mà không hỏi DNS bên ngoài | Không thể biết nguồn kết quả chỉ từ chuỗi địa chỉ được trả về |
| Cache kết quả thành công trong JVM | Các lần gọi sau **có thể** nhanh hơn | Thời gian nhanh không chứng minh cache hit |
| Cache kết quả thất bại | Các lần sau **có thể** ném `UnknownHostException` nhanh | Ngoại lệ nhanh không chứng minh có DNS NXDOMAIN ở lần trước |
| Cache và resolver của hệ điều hành | JVM có thể nhận kết quả từ tầng phía dưới | Không thể quy mọi lần cache hit cho riêng JVM |
| JIT, khởi tạo lớp, CPU, lịch chạy luồng và tải hệ thống | Các lần đo có thể dao động dù tên và cấu hình không đổi | Một hai số đo không phải số liệu benchmark ổn định |
| Thay đổi cấu hình, TTL, thứ tự địa chỉ, mạng | Kết quả hoặc độ trễ có thể khác về sau | Không được giả định hai lần gọi luôn tương đương |

`InetAddress` có cơ chế cache cho kết quả tra cứu thành công và thất bại. Hai security property liên quan là `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl`. Giá trị thực tế phụ thuộc cấu hình/runtime; đây là **security properties**, không nên mặc định rằng đặt chúng bằng `System.setProperty(...)` trong đoạn mã thử nghiệm sẽ thay đổi hành vi cache theo ý muốn. Khi cần kiểm chứng TTL, phải ghi rõ cấu hình của tiến trình JVM và các tầng cache phía dưới, đồng thời tránh suy ra giá trị mặc định cố định cho mọi JDK.

Java 18 đã bổ sung SPI phân giải tên qua **`java.net.spi.InetAddressResolverProvider`**. Trên JDK hỗ trợ cơ chế này, ứng dụng có thể sử dụng bộ phân giải mặc định hoặc bộ phân giải do provider được cấu hình cung cấp. Điều này càng củng cố nguyên tắc: hợp đồng của `InetAddress` là lấy địa chỉ hoặc báo không phân giải được; cách tạo kết quả có thể thay đổi theo môi trường.

## 5. Cách xây dựng thí nghiệm có thể kiểm chứng

**Bước 1 — Chỉ rõ câu hỏi.** Ví dụ: “Trong cùng tiến trình JVM và cùng môi trường mạng, thời gian của `getAllByName("service.example")` thay đổi thế nào sau lần gọi đầu?” Câu hỏi này chỉ yêu cầu đo thời gian API, không giả định có DNS trên mạng.

**Bước 2 — Chọn các nhóm đầu vào có ý nghĩa.** Dùng địa chỉ literal (`127.0.0.1`), tên cục bộ (`localhost`), và một tên do bạn kiểm soát trong môi trường thử nghiệm. Nếu dùng tên dự kiến không tồn tại, đánh dấu đó chỉ là kỳ vọng, không xem thất bại là bảo đảm. Tránh phụ thuộc vào việc một trang web công khai phải trả về IP cố định.

**Bước 3 — Ghi bối cảnh.** Lưu phiên bản JDK đang chạy, máy/hệ điều hành, cấu hình hosts, resolver và những thay đổi liên quan đến cache/TTL đã chủ động thiết lập. Chạy nhiều lượt, ghi kết quả từng lượt; nếu phân tích hiệu năng thì dùng phân bố và các phân vị thay vì một phép đo đơn lẻ.

**Bước 4 — Phân biệt bằng chứng.**

| Cần chứng minh | Dữ liệu tối thiểu cần có |
| --- | --- |
| Lời gọi API mất bao lâu | Khoảng `nanoTime()` và đầu vào, cùng kết quả hoặc ngoại lệ |
| Kết quả lặp lại trong JVM | Log nhiều lượt trong cùng tiến trình và bối cảnh cấu hình |
| Có truy vấn DNS phát sinh thực sự | Bản ghi truy vấn tại DNS server bạn kiểm soát hoặc thu thập lưu lượng mạng có thể đối chiếu; chỉ log Java là chưa đủ |
| Truy vấn đi qua tầng cache nào | Thông tin quan sát/cấu hình của từng tầng resolver/cache, với giới hạn đo được nêu rõ |

**Bước 5 — Viết kết luận theo bằng chứng.** Một kết luận tốt sẽ là: “Lần 2 và 3 của `getAllByName` nhanh hơn lần 1 trong lần chạy này; cache là một giả thuyết cần xác minh thêm.” Một kết luận không có cơ sở là: “Lần 1 gửi DNS, lần 2 không gửi DNS” nếu chỉ có số mili giây từ chương trình Java.

## 6. Bài tập phân tích kết quả

Xét ba tình huống giả định sau, mỗi tình huống chạy trong cùng một JVM:

| Quan sát | Cách diễn giải có căn cứ | Điều cần kiểm chứng thêm |
| --- | --- | --- |
| `localhost` trả kết quả sau 0,08 ms | Có địa chỉ được trả về rất nhanh | Tên được xử lý qua hosts, cache hay resolver nào? |
| `api.example` lần đầu 40 ms, lần sau 0,15 ms | Thời gian API giảm giữa hai lượt | Cache ở tầng nào, hay còn nguyên nhân khác? |
| `missing-host.invalid` ném `UnknownHostException` sau 0,12 ms | Lời gọi không trả về địa chỉ và mất 0,12 ms | Lỗi đến từ cấu hình, cache thất bại, provider hay DNS? |

Các số ở bảng **chỉ là dữ liệu minh họa**, không phải chuẩn hiệu năng hay kết quả cố định của Java 18. Hãy sửa chương trình để ghi thêm thời gian chạy theo đồng hồ thực (`Instant.now()`) **ngoài khoảng đo**, rồi so sánh các lần chạy ở thời điểm khác nhau. `Instant` giúp đối chiếu log với hệ thống bên ngoài; `nanoTime` tiếp tục dùng để tính thời gian đã trôi qua.

## 7. Ghi nhớ khi ứng dụng thực tế

1. `InetAddress.getAllByName` diễn đạt yêu cầu lấy địa chỉ của tên, **không** cam kết một lần gọi tương ứng một truy vấn DNS.
2. `UnknownHostException` nói rằng thao tác không xác định được địa chỉ theo cơ chế hiện hành; riêng ngoại lệ không tiết lộ chắc chắn mã phản hồi DNS hoặc sự tồn tại của gói tin.
3. `System.nanoTime()` đo thời gian lời gọi phía Java, bao gồm các tầng mà nó phải chờ; nó không tự tách thời gian xử lý DNS trên mạng.
4. Các yếu tố như literal IP, hosts, cache dương/âm, resolver hệ điều hành và `InetAddressResolverProvider` có thể thay đổi hành vi giữa các máy và các lần gọi.
5. Khi cần phát biểu về lưu lượng DNS, phải bổ sung bằng chứng quan sát DNS hoặc mạng; khi cần phát biểu về hiệu năng, phải đo lặp lại trong môi trường được ghi nhận rõ ràng.

Những nguyên tắc này giúp kiểm chứng **hợp đồng API và hành vi quan sát được** trên JDK hiện đại mà không phụ thuộc vào các chi tiết nội bộ, cấu hình cũ hoặc một giả định không được API bảo đảm.
