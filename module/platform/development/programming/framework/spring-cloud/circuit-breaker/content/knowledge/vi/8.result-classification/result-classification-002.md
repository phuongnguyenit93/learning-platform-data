# recordExceptions, ignoreExceptions và phạm vi ngoại lệ

Circuit breaker của Resilience4j quyết định một lời gọi có được tính là thành công hay thất bại dựa trên kết quả mà hàm được bảo vệ trả về. Với lời gọi ném ngoại lệ, ứng dụng có thể cấu hình loại ngoại lệ nào được ghi nhận là lỗi và loại nào cần bỏ qua. Hai thuộc tính quan trọng là `recordExceptions` và `ignoreExceptions`.

Phân loại đúng giúp circuit breaker phản ánh sự cố của dịch vụ phụ thuộc. Nếu mọi ngoại lệ nghiệp vụ đều bị tính là lỗi hạ tầng, mạch có thể mở dù dịch vụ vẫn hoạt động bình thường. Ngược lại, nếu bỏ qua cả timeout hoặc lỗi kết nối, circuit breaker có thể không nhận ra phụ thuộc đang gặp sự cố.

## Ba kết quả khi phân loại ngoại lệ

Với Resilience4j, một ngoại lệ phát sinh từ lời gọi được bảo vệ có thể thuộc một trong ba nhóm:

| Nhóm | Cách circuit breaker ghi nhận | Tác động đến tỷ lệ |
|---|---|---|
| **Được ghi nhận là thất bại** | Tăng số lời gọi thất bại. | Làm tăng failure rate. |
| **Bị bỏ qua** | Không tính là thành công cũng không tính là thất bại. | Không làm thay đổi hai bộ đếm kết quả trong cửa sổ. |
| **Không khớp danh sách ghi nhận hoặc bỏ qua** | Với cấu hình chỉ định `recordExceptions`, ngoại lệ không khớp danh sách này được xem là thành công, trừ khi nó thuộc danh sách bỏ qua. | Làm tăng số lời gọi thành công. |

Mặc định, nếu không cấu hình danh sách hoặc predicate phân loại riêng, ngoại lệ phát sinh từ lời gọi được ghi nhận là thất bại. Khi khai báo `recordExceptions`, ứng dụng chuyển sang cách chọn loại ngoại lệ được tính là thất bại. Vì vậy, cần hiểu rõ những ngoại lệ còn lại sẽ được phân loại ra sao.

## recordExceptions: chọn ngoại lệ được tính là lỗi

`recordExceptions` là danh sách các lớp ngoại lệ mà circuit breaker phải ghi nhận là thất bại. Đây thường là những lỗi thể hiện phụ thuộc không thể đáp ứng yêu cầu, chẳng hạn timeout, lỗi kết nối hoặc lỗi dịch vụ từ xa.

Ví dụ, dịch vụ đặt hàng gọi dịch vụ tồn kho. Những lỗi như `SocketTimeoutException` hoặc `InventoryUnavailableException` cho biết lời gọi không hoàn thành do phụ thuộc gặp vấn đề. Ứng dụng có thể cấu hình chúng vào danh sách ghi nhận.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
          - com.example.inventory.InventoryUnavailableException
~~~

Trong ví dụ, các ngoại lệ được liệt kê sẽ được tính là thất bại. Khi có ít nhất số mẫu tối thiểu và tỷ lệ thất bại đạt ngưỡng, circuit breaker có thể chuyển từ CLOSED sang OPEN.

Khi `recordExceptions` được cấu hình, ngoại lệ không khớp danh sách ghi nhận thường được tính là thành công, trừ các ngoại lệ được khai báo bỏ qua. Đây là điểm cần chú ý: một danh sách ghi nhận quá hẹp có thể vô tình xem nhiều lỗi không mong muốn là thành công.

## ignoreExceptions: loại ngoại lệ không tham gia thống kê

`ignoreExceptions` xác định các ngoại lệ mà circuit breaker không dùng để tính tỷ lệ thành công hoặc thất bại. Chúng thường đại diện cho kết quả nghiệp vụ có thể dự đoán hoặc dữ liệu đầu vào không hợp lệ, không phải sự cố của dịch vụ phụ thuộc.

Ví dụ:

- `InvalidSkuException`: mã sản phẩm do người dùng gửi không hợp lệ.
- `ProductNotFoundException`: sản phẩm không tồn tại theo quy tắc nghiệp vụ.
- `BusinessRuleViolationException`: yêu cầu vi phạm một quy tắc nghiệp vụ đã định nghĩa.

Có thể bổ sung danh sách bỏ qua vào cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
          - com.example.inventory.InventoryUnavailableException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.ProductNotFoundException
          - com.example.common.BusinessRuleViolationException
~~~

Ngoại lệ khớp `ignoreExceptions` được ưu tiên bỏ qua, kể cả khi kiểu ngoại lệ đó cũng khớp với một lớp trong `recordExceptions`. Ngoại lệ bị bỏ qua vẫn có thể được truyền ra khỏi lời gọi để tầng gọi xử lý hoặc fallback phản hồi. “Bỏ qua” ở đây chỉ có nghĩa là không tính ngoại lệ vào thống kê circuit breaker; nó không có nghĩa là nuốt ngoại lệ hay tự biến kết quả thành thành công.

Hãy chỉ bỏ qua các ngoại lệ thực sự không phản ánh sức khỏe của phụ thuộc. Nếu bỏ qua `SocketTimeoutException`, `ConnectException` hoặc lỗi máy chủ từ xa, mạch có thể tiếp tục đóng trong khi các lời gọi đang thất bại hàng loạt.

## Phân biệt lỗi nghiệp vụ và lỗi phụ thuộc

Việc phân loại cần dựa trên ý nghĩa của ngoại lệ trong luồng gọi cụ thể, không chỉ dựa trên tên lớp.

| Tình huống | Cách phân loại thường phù hợp | Lý do |
|---|---|---|
| Dịch vụ phụ thuộc không thể kết nối | Ghi nhận thất bại | Phụ thuộc không sẵn sàng để xử lý lời gọi. |
| Lời gọi vượt timeout | Ghi nhận thất bại | Phụ thuộc không đáp ứng trong ngân sách thời gian. |
| Dịch vụ từ xa trả lỗi máy chủ 5xx và client ném ngoại lệ | Ghi nhận thất bại | Thường thể hiện lỗi xử lý ở phụ thuộc. |
| Mã sản phẩm không hợp lệ | Bỏ qua | Đầu vào không hợp lệ không chứng minh phụ thuộc bị lỗi. |
| Sản phẩm không tồn tại theo nghiệp vụ | Bỏ qua hoặc trả kết quả miền nghiệp vụ | Đây có thể là kết quả hợp lệ, không phải sự cố hạ tầng. |
| Dịch vụ từ xa trả 4xx do xác thực hoặc quyền truy cập | Phân loại theo ngữ cảnh | Có thể là lỗi cấu hình tích hợp hoặc yêu cầu nghiệp vụ không hợp lệ. |
| Lỗi lập trình nội bộ trong dịch vụ gọi | Đánh giá riêng | Có thể không phản ánh tình trạng phụ thuộc, nhưng không nên tự động bỏ qua mọi lỗi runtime. |

Ví dụ, HTTP 404 có thể có nghĩa sản phẩm không tồn tại, còn HTTP 401 có thể cho thấy thông tin xác thực giữa các dịch vụ bị cấu hình sai. Không nên gom mọi lỗi HTTP 4xx thành một nhóm bỏ qua mà không hiểu nguyên nhân. Tương tự, không nên ghi nhận mọi ngoại lệ `RuntimeException` như lỗi phụ thuộc nếu nó có thể bao gồm lỗi lập trình hoặc vi phạm quy tắc nghiệp vụ.

Với các HTTP client, cần xem loại ngoại lệ thực tế mà client ném ra. Chẳng hạn, Spring WebClient có thể phát sinh `WebClientResponseException`; RestClient cũng có thể ném ngoại lệ phản ánh mã phản hồi HTTP. Hãy phân loại đúng kiểu ngoại lệ được truyền đến circuit breaker, hoặc chuyển đổi chúng thành các ngoại lệ miền rõ nghĩa tại ranh giới client.

## Phạm vi ngoại lệ: circuit breaker nhìn thấy điều gì?

Circuit breaker chỉ phân loại kết quả của phần công việc được bọc bởi nó. Với lời gọi đồng bộ, đó thường là supplier hoặc callable được truyền vào `run`. Ngoại lệ bị bắt và xử lý bên trong phần công việc sẽ không đi tới circuit breaker, do đó không được ghi nhận như ngoại lệ của lời gọi.

Ví dụ sau bắt ngoại lệ ngay bên trong supplier:

~~~java
return circuitBreaker.run(() -> {
    try {
        return inventoryService.find(sku);
    } catch (SocketTimeoutException ex) {
        log.warn("Inventory request timed out", ex);
        return Inventory.unavailable(sku);
    }
}, fallback);
~~~

Trong trường hợp này, supplier trả về `Inventory.unavailable(sku)` bình thường. Circuit breaker nhìn thấy một kết quả trả về, nên không thể biết rằng lời gọi bên trong đã timeout. Nếu muốn circuit breaker ghi nhận timeout, hãy để ngoại lệ phù hợp thoát khỏi supplier và xử lý nó ở fallback hoặc tầng gọi bên ngoài.

Cũng cần chú ý ngoại lệ bọc. Giả sử client ném `SocketTimeoutException`, nhưng lớp adapter bắt nó rồi ném `InventoryClientException` với nguyên nhân gốc là timeout. Circuit breaker nhận `InventoryClientException` ở ranh giới được bảo vệ. Nếu chỉ khai báo `SocketTimeoutException` trong `recordExceptions`, lớp bọc có thể không khớp danh sách đó. Hãy khai báo kiểu ngoại lệ thực sự thoát khỏi supplier, chọn một lớp cha phù hợp hoặc dùng predicate phân loại có xét nguyên nhân nếu phiên bản Resilience4j đang dùng hỗ trợ cách đó.

~~~java
public Inventory find(String sku) {
    try {
        return remoteClient.find(sku);
    } catch (SocketTimeoutException ex) {
        throw new InventoryClientException(
                "Inventory service timed out", ex
        );
    }
}
~~~

Với cách chuyển đổi trên, cấu hình cần nhận diện `InventoryClientException` nếu đó là kiểu thoát khỏi lời gọi được bảo vệ. Không nên giả định circuit breaker luôn tự duyệt toàn bộ chuỗi `cause` để tìm ngoại lệ bên trong.

## Cấu hình bằng Java

Ngoài application.yml, có thể xây dựng `CircuitBreakerConfig` bằng Java. Ví dụ sau dùng hai danh sách ngoại lệ:

~~~java
import java.io.IOException;
import java.net.SocketTimeoutException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .recordExceptions(
                IOException.class,
                SocketTimeoutException.class,
                InventoryUnavailableException.class
        )
        .ignoreExceptions(
                InvalidSkuException.class,
                ProductNotFoundException.class
        )
        .build();
~~~

Sau đó, có thể áp dụng cấu hình cho một ID thông qua factory Resilience4j của Spring Cloud CircuitBreaker:

~~~java
@Bean
public Customizer<Resilience4JCircuitBreakerFactory>
        inventoryCircuitBreakerConfiguration() {

    return factory -> factory.configure(
            builder -> builder.circuitBreakerConfig(config).build(),
            "inventory-read"
    );
}
~~~

Đoạn cấu hình trên minh họa cách gắn chính sách cho ID `inventory-read`. Trong dự án thực tế, hãy đặt `config` ở bean hoặc phương thức tạo cấu hình phù hợp để Spring quản lý vòng đời, đồng thời dùng đúng package và phiên bản starter đang được dự án quản lý.

Không nên đồng thời cấu hình cùng một instance bằng nhiều nguồn mà không xác định rõ nguồn nào có hiệu lực. Nếu dùng application.yml cho danh sách ngoại lệ và Java customizer cho một phần cấu hình khác, hãy kiểm tra cách factory kết hợp chúng theo phiên bản đang sử dụng.

## Kết hợp phân loại ngoại lệ với fallback

Fallback quyết định ứng dụng trả gì khi lời gọi thất bại hoặc circuit breaker từ chối thực thi vì đang OPEN. Việc phân loại ngoại lệ và việc chọn fallback là hai trách nhiệm khác nhau.

~~~java
public Inventory findInventory(String sku) {
    return circuitBreakerFactory.create("inventory-read").run(
            () -> inventoryClient.find(sku),
            error -> {
                if (error instanceof ProductNotFoundException) {
                    return Inventory.notFound(sku);
                }
                return Inventory.unavailable(sku);
            }
    );
}
~~~

Đây là ví dụ minh họa các phương thức của mô hình `Inventory`. Nếu `ProductNotFoundException` được cấu hình bỏ qua, circuit breaker không tăng failure count cho ngoại lệ đó, nhưng fallback vẫn có thể nhận ngoại lệ và chuyển nó thành kết quả nghiệp vụ. Nếu `InventoryUnavailableException` được ghi nhận là thất bại, fallback có thể trả trạng thái tạm thời hoặc dữ liệu cache.

Không nên để fallback che giấu mọi lỗi bằng một kết quả mặc định có vẻ hợp lệ. Chẳng hạn, trả tồn kho bằng 0 khi không kết nối được dịch vụ có thể khiến hệ thống từ chối đơn hàng sai; trả số lượng cache cũ mà không đánh dấu cũng có thể khiến hệ thống chấp nhận đơn hàng vượt tồn kho. Hãy biểu diễn rõ trạng thái dữ liệu và mức độ tin cậy của fallback.

Nếu fallback tự ném ngoại lệ, ngoại lệ đó có thể tiếp tục truyền tới caller. Việc này không thay đổi phân loại ban đầu của supplier đã được circuit breaker ghi nhận; hãy xử lý lỗi fallback ở ranh giới phù hợp và ghi nhận riêng để theo dõi.

## Kiểm thử phân loại ngoại lệ

Nên kiểm tra từng nhóm ngoại lệ bằng các lời gọi có kết quả xác định. Với cửa sổ đếm, đặt số lời gọi tối thiểu nhỏ trong môi trường kiểm thử để dễ quan sát chuyển trạng thái.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Supplier ném ngoại lệ có trong `recordExceptions` | Failure count tăng. |
| Supplier ném ngoại lệ có trong `ignoreExceptions` | Không tăng success count hoặc failure count. |
| Supplier ném ngoại lệ không khớp danh sách khi đã cấu hình `recordExceptions` | Được tính là thành công, trừ khi có quy tắc bỏ qua phù hợp. |
| Một ngoại lệ khớp cả danh sách ghi nhận và bỏ qua | Quy tắc bỏ qua được ưu tiên. |
| Supplier bắt ngoại lệ rồi trả kết quả bình thường | Circuit breaker ghi nhận kết quả trả về, không thấy ngoại lệ đã bị bắt. |
| Adapter bọc timeout trong ngoại lệ miền | Xác nhận kiểu ngoại lệ ở ranh giới supplier được phân loại đúng. |
| Ngoại lệ bị bỏ qua đi qua fallback | Fallback vẫn có thể xử lý ngoại lệ được truyền ra. |
| Mạch đang OPEN | Lời gọi mới bị từ chối; fallback xử lý trường hợp không được phép gọi. |

Khi kiểm tra, hãy quan sát số lời gọi thành công, thất bại, bị bỏ qua và trạng thái circuit breaker. Nếu một ngoại lệ nghiệp vụ làm failure rate tăng, xem lại danh sách ghi nhận và bỏ qua. Nếu timeout không làm failure rate tăng, kiểm tra ngoại lệ thực tế ở ranh giới supplier, cách chuyển đổi ngoại lệ và việc có bắt lỗi quá sớm hay không.

## Nguyên tắc thiết kế

1. Xác định ngoại lệ nào thể hiện phụ thuộc không sẵn sàng hoặc không đáp ứng đúng thời hạn.
2. Dùng `recordExceptions` để ghi nhận các kiểu lỗi cần tác động đến failure rate.
3. Dùng `ignoreExceptions` cho lỗi nghiệp vụ hoặc đầu vào không hợp lệ không phản ánh sức khỏe của phụ thuộc.
4. Nhớ rằng khi cấu hình danh sách ghi nhận, ngoại lệ không khớp danh sách thường được tính là thành công nếu không bị bỏ qua.
5. Phân loại theo kiểu ngoại lệ thực sự thoát khỏi phần công việc được bảo vệ; chú ý ngoại lệ bị bắt hoặc bọc lại.
6. Để fallback xử lý kết quả cho caller, nhưng giữ riêng ý nghĩa phân loại của circuit breaker.
7. Kiểm thử cả lỗi nhanh, timeout, lỗi nghiệp vụ và ngoại lệ bọc trước khi đưa cấu hình vào vận hành.

Với Spring Cloud CircuitBreaker tích hợp Resilience4j, phân loại ngoại lệ chính xác giúp sliding window phản ánh đúng lỗi của phụ thuộc. `recordExceptions` xác định những lỗi được tính vào failure rate; `ignoreExceptions` loại các ngoại lệ không liên quan đến sức khỏe phụ thuộc khỏi thống kê. Khi xác định đúng ranh giới lời gọi và kiểu ngoại lệ thực tế, circuit breaker có thể mở khi cần bảo vệ hệ thống mà không phản ứng sai với các kết quả nghiệp vụ bình thường.

