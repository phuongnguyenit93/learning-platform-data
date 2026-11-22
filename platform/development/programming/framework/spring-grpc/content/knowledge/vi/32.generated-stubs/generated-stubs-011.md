# Không chia sẻ stub với channel đã đóng

## 1. Mục tiêu

Trong gRPC Java, generated stub giữ tham chiếu tới một Channel. Ứng dụng có thể tái sử dụng stub giữa nhiều request vì stub là immutable, nhưng chỉ an toàn khi channel mà stub sử dụng vẫn còn trong vòng đời hoạt động. Nếu một component đóng ManagedChannel trong khi các gateway khác vẫn giữ stub được tạo từ channel đó, những RPC mới qua các stub ấy sẽ thất bại.

**Không chia sẻ stub với channel đã đóng** nghĩa là không tiếp tục dùng generated stub sau khi ManagedChannel mà nó tham chiếu đã đi vào trạng thái shutdown. Stub không sở hữu kết nối và không thể tự mở lại channel. Muốn tiếp tục gọi RPC, ứng dụng phải tạo channel mới và stub mới từ channel đó, rồi chuyển consumer sang cặp mới theo một quy trình có kiểm soát.

Sau bài học, bạn có thể:

- Giải thích vì sao stub vẫn tồn tại nhưng không thể gọi qua channel đã đóng.
- Phân biệt channel đang reconnect với channel đã shutdown.
- Hiểu khác biệt giữa shutdown() và shutdownNow().
- Quản lý channel bằng một lifecycle owner trong Spring.
- Tránh gateway hoặc application service tự đóng channel dùng chung.
- Thay channel và stub đồng bộ khi cần rotate hoặc khởi tạo lại client.
- Kiểm thử lỗi khi dùng stub cũ và xác minh stub mới hoạt động.

## 2. Stub giữ channel, không sở hữu channel

Generated stub trong gRPC Java là facade immutable cho service API. Khi tạo stub:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel);
```

Stub giữ channel được truyền vào cùng cấu hình call options. Khi gọi RPC, generated stub tạo call trên chính channel đó. Stub không tạo channel thay thế và không sở hữu quyền đóng transport.

Điều này có hai hệ quả:

- Có thể tạo nhiều stub hoặc stub dẫn xuất từ cùng channel và tái sử dụng chúng đồng thời khi channel còn hoạt động.
- Nếu channel bị shutdown, mọi stub đang tham chiếu channel đó đều chịu ảnh hưởng, kể cả stub được tạo qua withDeadlineAfter(), withInterceptors() hoặc call options khác.

Ví dụ:

```java
var baseStub = CatalogServiceGrpc.newBlockingStub(channel);
var shortStub = baseStub.withDeadlineAfter(
        300, TimeUnit.MILLISECONDS);
var longStub = baseStub.withDeadlineAfter(
        2, TimeUnit.SECONDS);
```

baseStub, shortStub và longStub là ba object stub khác nhau nhưng cùng dùng một channel. Đóng channel làm cả ba không thể bắt đầu RPC mới.

## 3. Channel shutdown là trạng thái kết thúc

ManagedChannel có lifecycle riêng. Khi gọi shutdown():

- Channel ngừng nhận RPC mới.
- Các RPC đã được chấp nhận có cơ hội hoàn tất.
- Khi các call đang chạy kết thúc, channel tiến tới terminated.
- Không thể đưa chính channel object đó trở lại trạng thái hoạt động.

Một call mới qua stub cũ sau khi channel shutdown thường thất bại với status UNAVAILABLE. Ứng dụng không nên dựa vào việc stub vẫn là object hợp lệ hoặc tạo stub không ném lỗi để kết luận channel còn dùng được.

shutdownNow() mạnh hơn: yêu cầu hủy các call đang hoạt động và đóng channel nhanh hơn. Dùng nó khi hết thời gian graceful shutdown hoặc khi cần dừng khẩn cấp.

| Trạng thái/hành động | Ý nghĩa | Có thể dùng stub để bắt đầu RPC mới? |
|---|---|---|
| Channel đang hoạt động | Nhận call theo trạng thái kết nối hiện tại | Có |
| Channel tạm thời mất kết nối nhưng chưa shutdown | Có thể reconnect theo policy của channel | Có thể; call phụ thuộc deadline/readiness |
| Đã gọi shutdown() | Không nhận call mới; call đang chạy được drain | Không |
| Đã gọi shutdownNow() | Hủy call đang chạy và đóng channel | Không |
| Channel terminated | Lifecycle đã kết thúc | Không |

Một lỗi mạng hoặc server tạm thời không đồng nghĩa channel đã đóng. ManagedChannel có thể tự reconnect khi transport phục hồi. Không tạo channel mới mỗi khi nhận UNAVAILABLE; trước tiên cần xác định lỗi là outage tạm thời, deadline, routing hay channel đã shutdown.

## 4. Vì sao không thể mở lại stub cũ?

Các phương thức cấu hình stub như withDeadlineAfter() hoặc withCallCredentials() tạo stub dẫn xuất nhưng vẫn giữ cùng channel:

```java
var newDeadlineStub = oldStub.withDeadlineAfter(
        1, TimeUnit.SECONDS);
```

Đoạn code trên chỉ thay call options. Nó không gọi ManagedChannelBuilder, không tạo transport mới và không thay channel reference. Vì vậy, nếu oldStub tham chiếu channel đã shutdown thì newDeadlineStub cũng không sử dụng được.

Muốn khôi phục khả năng gọi RPC, phải tạo cặp mới:

```java
ManagedChannel replacementChannel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub replacementStub =
        CatalogServiceGrpc.newBlockingStub(replacementChannel);
```

replacementStub dùng replacementChannel; nó không phụ thuộc channel cũ. Sau khi chuyển consumer sang cặp mới và drain call cũ, channel cũ mới được shutdown.

## 5. Một lifecycle owner cho channel dùng chung

Trong Spring, channel thường được tạo như bean dùng chung. Component tạo channel hoặc được giao quyền sở hữu channel phải quản lý shutdown. Các gateway chỉ nhận channel/stub qua dependency injection không tự đóng tài nguyên đó.

Ví dụ:

```java
@Configuration
public class CatalogGrpcClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        return CatalogServiceGrpc.newBlockingStub(channel);
    }
}
```

Gateway chỉ sử dụng stub:

```java
@Component
public class CatalogGateway {

    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    public CatalogGateway(
            CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Product getProduct(String productId) {
        var request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();

        return stub.withDeadlineAfter(700, TimeUnit.MILLISECONDS)
                .getProduct(request);
    }
}
```

destroyMethod = "shutdown" yêu cầu Spring gọi shutdown khi bean bị hủy. CatalogGateway không có trách nhiệm shutdown channel. Nếu Spring gRPC starter đang tự quản lý channel, hãy dùng lifecycle API của starter thay vì tạo owner thứ hai.

Không đặt channel.shutdown() trong:

- Method xử lý một request nghiệp vụ.
- @PreDestroy của gateway chỉ đang mượn channel.
- Cleanup của một test consumer khi channel còn được test khác dùng chung.
- Error handler chạy khi một RPC gặp UNAVAILABLE.

Đóng channel ở consumer có thể làm hỏng mọi bean khác đang dùng chung channel.

## 6. Graceful shutdown và force shutdown

Khi application dừng bình thường, ưu tiên cho RPC đang chạy hoàn tất trong một khoảng thời gian hữu hạn:

```java
static void shutdownGracefully(
        ManagedChannel channel,
        Duration gracePeriod) {
    channel.shutdown();
    try {
        if (!channel.awaitTermination(
                gracePeriod.toMillis(), TimeUnit.MILLISECONDS)) {
            channel.shutdownNow();
            channel.awaitTermination(1, TimeUnit.SECONDS);
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

Ví dụ minh họa trình tự shutdown. Trong ứng dụng Spring, đặt logic đó ở lifecycle owner hoặc cơ chế graceful shutdown được framework/starter hỗ trợ; không gọi từ gateway. Thời gian grace phải phù hợp với thời gian shutdown tổng của ứng dụng và deadline tối đa của RPC.

awaitTermination() chỉ chờ channel kết thúc; nó không làm channel sống lại. Nếu thời gian chờ hết, shutdownNow() buộc hủy call còn lại. Sau khi channel đã shutdown, không dùng lại stub cũ cho request tiếp theo.

## 7. Phân biệt reconnect với channel đã đóng

Một ManagedChannel có thể đi qua trạng thái IDLE, CONNECTING, READY, TRANSIENT_FAILURE và SHUTDOWN. Các trạng thái kết nối có thể thay đổi khi mạng hoặc server phục hồi; SHUTDOWN là trạng thái kết thúc.

| Tình huống | Cách xử lý |
|---|---|
| Server tạm thời không reachable, channel chưa shutdown | Cho channel thực hiện reconnect; áp dụng deadline/retry phù hợp |
| Channel đang CONNECTING hoặc TRANSIENT_FAILURE | Call có thể chờ hoặc thất bại tùy wait-for-ready và deadline |
| Ứng dụng chủ động gọi shutdown() | Xem channel là đã retire; tạo channel mới nếu cần tiếp tục |
| Channel đã TERMINATED | Không thể tái sử dụng |
| RPC trả UNAVAILABLE nhưng channel vẫn hoạt động | Điều tra server, proxy, name resolution, load balancing và retry policy trước khi thay channel |

getState(true) có thể giúp quan sát trạng thái channel, nhưng READY không bảo đảm một RPC cụ thể sẽ thành công; trạng thái có thể thay đổi ngay sau khi đọc. Health check RPC của service mới cung cấp tín hiệu về sức khỏe nghiệp vụ, còn channel state chỉ phản ánh trạng thái kết nối phía client.

Không dùng việc tạo channel mới như phản xạ cho mọi lỗi RPC. Điều đó có thể gây connection churn, TLS handshake lặp, tăng socket và làm sự cố tải nặng hơn.

## 8. Thay channel phải thay cả stub

Khi rotate endpoint, certificate hoặc cần khởi tạo lại channel sau một lifecycle kết thúc, hãy tạo một generation client mới gồm channel và stub tương ứng:

```java
record CatalogClientGeneration(
        ManagedChannel channel,
        CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
}

static CatalogClientGeneration createGeneration(
        String host,
        int port) {
    ManagedChannel channel = ManagedChannelBuilder
            .forAddress(host, port)
            .useTransportSecurity()
            .build();

    var stub = CatalogServiceGrpc.newBlockingStub(channel);
    return new CatalogClientGeneration(channel, stub);
}
```

Generation đóng gói hai đối tượng phải có cùng vòng đời. Consumer nhận stub từ generation hiện hành; khi tạo generation mới, stub mới phải được tạo từ channel mới.

Một cách cutover đơn giản khi ứng dụng có thể tạm ngừng nhận request:

1. Ngừng nhận hoặc tạm khóa request mới đi tới gateway.
2. Chờ call đang chạy qua generation cũ hoàn tất trong giới hạn cho phép.
3. Tạo channel mới và stub mới.
4. Chuyển gateway sang generation mới.
5. Xác minh call mới hoạt động.
6. Shutdown channel cũ sau khi không còn consumer dùng generation cũ.

Nếu cần rotate không gián đoạn, phải có cơ chế lease/reference count hoặc drain coordination để bảo đảm không có thread vừa lấy generation cũ nhưng chưa bắt đầu call khi channel cũ bị shutdown. Chỉ dùng AtomicReference để thay generation rồi shutdown ngay channel cũ có thể tạo race ở ranh giới đó. Cơ chế hot-swap cần được thiết kế và kiểm thử riêng.

## 9. Không giữ stub cũ trong singleton sau khi rotate

Một lỗi thường gặp là cập nhật channel trong configuration nhưng gateway vẫn giữ field stub cũ:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;
    // Stub được tạo từ channel cũ.
}
```

Việc tạo replacementChannel ở nơi khác không thay đổi reference đã lưu trong gateway. Những call tiếp theo vẫn đi qua channel cũ.

Nếu channel được cấu hình cố định theo application context, giải pháp đơn giản nhất là restart/refresh context theo cơ chế được hỗ trợ để Spring tạo lại cả channel bean và stub bean. Nếu ứng dụng cần runtime rotation, inject một client provider/holder có khả năng thay generation đồng bộ thay vì inject trực tiếp một stub cố định.

Không sửa reflection hoặc field private của generated stub để thay channel. Stub immutable là một phần thiết kế API; tạo stub mới từ channel mới là cách đúng.

## 10. Kiểm thử stub sau khi channel đóng

Một test có thể chứng minh stub cũ không còn dùng được sau shutdown và stub mới hoạt động qua channel mới. Với in-process transport:

```java
@Test
void stubCannotStartNewCallAfterItsChannelIsShutdown()
        throws Exception {
    String oldName = InProcessServerBuilder.generateName();
    Server oldServer = InProcessServerBuilder.forName(oldName)
            .directExecutor()
            .addService(new FakeCatalogService())
            .build()
            .start();
    ManagedChannel oldChannel =
            InProcessChannelBuilder.forName(oldName)
                    .directExecutor()
                    .build();

    var oldStub = CatalogServiceGrpc.newBlockingStub(oldChannel);
    oldChannel.shutdown();
    assertTrue(oldChannel.awaitTermination(2, TimeUnit.SECONDS));

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> oldStub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("product-42")
                            .build()));

    assertEquals(Status.Code.UNAVAILABLE,
            error.getStatus().getCode());

    oldServer.shutdownNow();
    oldServer.awaitTermination(2, TimeUnit.SECONDS);
}
```

Đây là test minh họa cho call mới sau khi channel shutdown. Trong test thực tế, đặt cleanup server/channel trong try/finally hoặc JUnit lifecycle để tài nguyên luôn được đóng kể cả khi assertion thất bại.

Test tiếp theo cần tạo server/channel mới, tạo stub mới từ channel mới và xác minh RPC thành công. Không dùng lại oldStub:

```java
ManagedChannel replacementChannel =
        InProcessChannelBuilder.forName(newServerName)
                .directExecutor()
                .build();

var replacementStub =
        CatalogServiceGrpc.newBlockingStub(replacementChannel);

Product product = replacementStub.getProduct(request);
```

Trong test này newServerName phải trỏ tới server fixture đang chạy. Test cần đóng replacement channel và server trong cleanup.

## 11. Kiểm thử Spring lifecycle

Unit test channel có thể chứng minh behavior của gRPC Java, nhưng chưa chứng minh Spring đóng đúng bean hoặc không có consumer giữ stub cũ. Một Spring integration test nên xác minh:

- Context tạo một channel bean cho target.
- Các stub/gateway nhận đúng channel generation.
- Gateway không tự shutdown channel khi bean khác vẫn cần dùng.
- Khi context đóng, channel owner thực hiện shutdown.
- Sau khi context cũ đã đóng, không tiếp tục gọi gateway cũ.
- Khi context mới được tạo, channel và stub mới được inject.

Nếu ứng dụng hỗ trợ refresh hoặc certificate rotation khi đang chạy, test cutover với call đồng thời: một nhóm call đang chạy trên channel cũ, một nhóm call mới sau khi switch, và không có call mới nào bị gửi vào channel đã shutdown.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Stub còn object nhưng RPC trả UNAVAILABLE | Channel mà stub giữ đã shutdown | Tạo channel và stub mới |
| withDeadlineAfter() không khôi phục call | Stub dẫn xuất vẫn dùng channel cũ | Tạo stub từ replacement channel |
| Gateway A làm Gateway B lỗi | A đóng channel dùng chung | Chỉ lifecycle owner được shutdown |
| Mỗi lỗi UNAVAILABLE lại tạo channel | Nhầm outage tạm thời với shutdown | Kiểm tra channel lifecycle và nguyên nhân transport |
| Call đang chạy bị cắt khi app dừng | Dùng shutdownNow() ngay lập tức | Graceful shutdown và grace period |
| Channel mới được tạo nhưng call vẫn lỗi | Gateway còn giữ stub cũ | Thay cả client generation hoặc recreate bean |
| Rotate channel gây lỗi ngẫu nhiên | Shutdown channel cũ trước khi consumer ngừng lấy nó | Dùng quiescence hoặc lease/drain coordination |
| Spring context đóng nhưng channel vẫn sống | Không có lifecycle owner rõ ràng | Quản lý channel bean/destroy lifecycle |
| Test pass nhưng production rotation lỗi | Chỉ test một call đơn lẻ, không test concurrency | Thêm cutover test với call đang chạy |

## 13. Bài tập thực hành

**Tình huống:** Một Spring application có CatalogGateway và RecommendationGateway cùng dùng một ManagedChannel. Một thành phần đang đóng channel khi hoàn tất tác vụ riêng; sau đó cả hai gateway đều bắt đầu nhận UNAVAILABLE. Nhóm muốn thay endpoint Catalog mà không để stub cũ tiếp tục được sử dụng.

Hãy thực hiện:

1. Xác định component nào tạo channel và component nào thực sự sở hữu lifecycle.
2. Loại bỏ shutdown khỏi gateway/consumer chỉ mượn channel.
3. Tạo một client generation gồm ManagedChannel và generated stub tương ứng.
4. Phân biệt channel shutdown với channel đang reconnect khi gặp UNAVAILABLE.
5. Viết test chứng minh stub cũ không thể tạo RPC mới sau shutdown.
6. Tạo channel/stub generation mới và xác minh RPC hoạt động.
7. Thiết kế cutover: quiesce request hoặc dùng lease/drain coordination trước khi shutdown generation cũ.
8. Kiểm thử call đang chạy, call mới và Spring context shutdown.
9. Xác minh không còn gateway nào giữ stub từ generation đã retire.

**Tiêu chí hoàn thành:** chỉ một owner đóng channel; mọi stub dùng chung được xem là hết hiệu lực khi channel shutdown; generation mới luôn tạo stub từ channel mới; call đang chạy được drain hoặc hủy theo policy; không có request mới đi vào channel đã retire.

## 14. Ghi nhớ

Generated stub giữ tham chiếu tới channel được truyền khi tạo; stub dẫn xuất vẫn dùng channel đó. Khi ManagedChannel shutdown, không thể khôi phục nó bằng cách tạo thêm stub hoặc đổi deadline. shutdown() ngừng nhận call mới và cho call hiện tại drain; shutdownNow() buộc hủy call còn lại. Phân biệt channel đang reconnect với channel đã shutdown để tránh tạo kết nối mới không cần thiết. Trong Spring, chỉ lifecycle owner đóng channel. Khi cần thay channel, tạo generation mới gồm channel và stub mới, chuyển consumer có kiểm soát rồi drain và đóng generation cũ. Không chia sẻ hoặc tiếp tục gọi stub tham chiếu channel đã đóng.
