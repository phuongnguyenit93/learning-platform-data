# Thiết kế adapter và lớp trung gian giữ hợp đồng cũ

## 1. Bối cảnh: tiến hóa API mà không làm gián đoạn client

Trong một đợt **Java Advance Compatibility Migration**, nhóm phát triển có thể cần thay phiên bản JDK, nâng framework, thay thư viện hoặc tổ chức lại phần triển khai nghiệp vụ. Các thay đổi đó thường tác động đến API mà module khác, plugin, ứng dụng đã triển khai hoặc đối tác đang sử dụng.

Giả sử thư viện phiên bản cũ công bố một phương thức nhận DTO truyền thống và trả về số tiền dưới dạng số nguyên. Ở kiến trúc mới, nghiệp vụ dùng domain model, service có dependency injection và kiểu số tiền chính xác hơn. Nếu thay trực tiếp chữ ký cũ, các client phải cập nhật đồng thời. Thực tế có thể tồn tại những client đã được biên dịch, đóng gói hoặc triển khai riêng nên không thể nâng trong cùng một thời điểm.

**Adapter** là thành phần chuyển đổi giữa hợp đồng cũ và mô hình mới: nó nhận yêu cầu theo API cũ, chuyển thành dữ liệu/lời gọi mà phần triển khai mới hiểu, rồi chuyển kết quả hoặc lỗi về hình thức mà client cũ mong đợi. **Lớp trung gian** là ranh giới tổ chức các adapter, facade, mapper và chính sách tương thích để sự thay đổi bên trong không lan trực tiếp đến client bên ngoài.

Mục tiêu là:

- Duy trì khả năng sử dụng API cũ trong khoảng thời gian chuyển tiếp đã cam kết.
- Cho phép phần lõi tiếp tục phát triển trên mô hình, dependency và framework mới.
- Tập trung logic ánh xạ, xử lý lỗi và các khác biệt ngữ nghĩa vào một ranh giới rõ ràng.
- Có thể kiểm thử riêng các cam kết của API cũ và của API mới.
- Hỗ trợ di chuyển dần client, theo dõi mức sử dụng và loại bỏ phần tương thích khi đủ điều kiện.

Không phải mọi thay đổi API đều cần một adapter. Nếu API chỉ dùng nội bộ, toàn bộ client được nâng cấp và kiểm chứng đồng thời, việc sửa trực tiếp có thể phù hợp. Adapter đặc biệt có giá trị khi hợp đồng cũ đã phát hành, có nhiều consumer hoặc có ràng buộc tương thích trong thời gian migration.

## 2. Xác định chính xác “hợp đồng cũ”

Giữ lại tên lớp hoặc tên phương thức chưa đủ để đảm bảo tương thích. Hợp đồng có nhiều lớp, từ mã nguồn đến hành vi và dữ liệu truyền qua mạng.

| Lớp hợp đồng | Nội dung cần giữ hoặc xác minh | Ví dụ thay đổi gây lỗi |
|---|---|---|
| Source API | Tên package, kiểu public, constructor, phương thức, generic, checked exception và khả năng biên dịch lại. | Xóa constructor không tham số; đổi kiểu tham số; chuyển class thành interface. |
| Binary API | Tên nhị phân, method descriptor, field descriptor, static/instance, class/interface, khả năng client bytecode cũ liên kết được. | Client cũ dùng invokestatic nhưng phương thức mới chỉ còn instance. |
| Behavioral | Giá trị trả về, quy tắc null, validation, exception, thứ tự xử lý, transaction, retry, tính xác định và thread-safety. | Thay vì trả mã lỗi cũ, API mới ném exception khác. |
| Wire/API giao tiếp | Endpoint, HTTP method/status, tên field JSON, định dạng ngày giờ, event name, schema và version. | Đổi field totalCents thành totalAmount trong response v1. |
| Operational | Timeout, idempotency, quyền truy cập, logging, metric, tính sẵn sàng và khả năng rollback. | Adapter tự retry tác vụ ghi và tạo đơn hàng hai lần. |

Khi xây dựng adapter, nên bắt đầu từ một bản mô tả hợp đồng đã được consumer quan sát thực tế: artifact đã phát hành, API documentation, test và log tương tác. Source code hiện tại có thể đã thay đổi so với version client thực sự sử dụng.

### 2.1. Lập danh sách consumer và phiên bản

Để thiết kế đúng ranh giới, cần biết:

1. Những module nào gọi trực tiếp class hoặc method Java cũ?
2. Consumer nào được build cùng repository, consumer nào giữ binary cũ?
3. Những HTTP client, message consumer, batch job hoặc plugin nào đang dùng hợp đồng cũ?
4. Consumer nào bắt buộc phải tương thích trong thời gian chuyển tiếp?
5. Hợp đồng cũ được duy trì đến mốc nào và ai chịu trách nhiệm di chuyển?

Một facade có thể giữ source API nhưng lại phá binary API nếu thay modifier, kiểu class hoặc constructor. Tương tự, endpoint HTTP có thể giữ đường dẫn nhưng làm client lỗi nếu status code hoặc payload thay đổi. Vì vậy, danh sách consumer và cam kết của từng lớp hợp đồng phải có trước quyết định thiết kế.

### 2.2. Phân biệt cam kết với hành vi vô tình

Không phải mọi chi tiết của implementation cũ đều là hợp đồng có chủ đích. Tuy nhiên, nếu client đang phụ thuộc vào một hành vi đã quan sát được, thay đổi hành vi đó vẫn có thể gây regression.

Ví dụ, API cũ trả về danh sách rỗng khi không có dữ liệu, trong khi API mới trả null. Nếu consumer dùng vòng lặp không kiểm tra null, thay đổi này có thể làm ứng dụng lỗi. Adapter nên duy trì danh sách rỗng cho endpoint/method cũ hoặc đưa ra kế hoạch thay đổi version rõ ràng.

Ngược lại, nếu implementation cũ có một lỗi nguy hiểm cần khắc phục, nhóm không nhất thiết giữ nguyên lỗi đó. Cần đánh giá rủi ro, tài liệu hóa thay đổi và bổ sung kiểm thử để đảm bảo quyết định có chủ đích.

## 3. Cấu trúc adapter và lớp trung gian

Một cấu trúc thông dụng:

~~~text
Client cũ                  Client mới
    │                          │
    ▼                          ▼
API / Facade cũ          API / Facade mới
    │                          │
    ▼                          │
Legacy Adapter                │
    │                          │
    ├── Legacy DTO mapper      │
    ├── Exception mapper       │
    └── Compatibility policy   │
                │              │
                ▼              ▼
          Application Service / Use Case
                       │
                       ▼
                 Domain / Core
                       │
                       ▼
           Infrastructure / External Adapter
~~~

Trong mô hình này, client cũ và client mới dùng hai đầu vào khác nhau, nhưng đều kết nối đến use case chung. Adapter cũ chứa phần chuyển đổi cần thiết. Phần lõi không cần biết các tên DTO, error code hoặc framework đã lỗi thời chỉ để phục vụ client cũ.

### 3.1. Phân biệt các kiểu lớp trung gian

| Thành phần | Vai trò | Khi nào cần |
|---|---|---|
| Adapter | Chuyển kiểu dữ liệu, lời gọi hoặc giao thức từ interface này sang interface khác. | API cũ và service mới có chữ ký hoặc cách biểu diễn khác nhau. |
| Facade | Cung cấp điểm vào đơn giản, ổn định trước nhiều thành phần bên trong. | Cần giữ một lớp API public trong khi thay đổi cấu trúc nội bộ. |
| Anti-corruption layer | Cô lập thuật ngữ, mô hình dữ liệu và giả định của hệ thống cũ khỏi domain mới. | Hai hệ thống có mô hình nghiệp vụ hoặc vocabulary khác nhau. |
| Mapper | Chuyển đổi DTO, enum, identifier, money, thời gian hoặc error response. | Dữ liệu cũ và mới không có cấu trúc/đơn vị giống nhau. |
| Proxy / Gateway | Điều phối việc truy cập service, transport, retry hoặc quan sát từ một ranh giới. | Có dịch vụ ngoài, kết nối từ xa hoặc cơ chế truy cập cần cô lập. |

Các khái niệm này có thể phối hợp. Facade giữ API public, adapter thực hiện lời gọi, mapper chuyển DTO, còn policy tương thích quy định cách xử lý ngoại lệ. Không cần tạo một class cho mỗi tên mẫu thiết kế nếu điều đó làm luồng đơn giản trở nên khó hiểu; ranh giới trách nhiệm mới là yếu tố quan trọng.

### 3.2. Hướng phụ thuộc

Lớp tương thích thường được phép biết mô hình cũ và mô hình mới. Phần lõi mới nên phụ thuộc vào abstraction nội bộ, không import DTO cũ của framework hoặc package legacy.

~~~text
legacy-api module
  └─ LegacyOrderFacade
       └─ LegacyOrderAdapter
            ├─ LegacyOrderMapper
            ├─ LegacyErrorMapper
            └─ OrderUseCase (abstraction)

application-core module
  ├─ OrderUseCase
  ├─ OrderCommand
  └─ OrderResult

infrastructure module
  └─ DefaultOrderUseCase / adapters
~~~

Nếu phần lõi mới phải trả về LegacyOrderDto hoặc ném LegacyHttpException cho mọi client, lớp tương thích đã bị đẩy ngược vào domain. Khi đó, việc loại bỏ API cũ về sau sẽ khó hơn nhiều.

## 4. Ví dụ: giữ API Java cũ và chuyển sang service mới

Xét thư viện cung cấp API tính giá. Hợp đồng cũ cho phép tạo đối tượng bằng constructor không tham số và gọi phương thức quote, trả giá trị theo đơn vị tiền nhỏ nhất (ví dụ: xu), dưới dạng int.

Phiên bản đã phát hành:

~~~java
package com.example.pricing.legacy;

public class LegacyPriceApi {
    public LegacyPriceApi() {
    }

    public int quote(String sku, int quantity)
            throws LegacyPricingException {
        return LegacyPricingEngine.quote(sku, quantity);
    }
}
~~~

Trong lần migration, phần lõi chuyển sang một use case hiện đại với kiểu kết quả long để có dải giá trị lớn hơn:

~~~java
package com.example.pricing.application;

public record PriceQuery(String sku, int quantity) {
}

public record PriceQuote(long amountInMinorUnits) {
}

public interface PricingUseCase {
    PriceQuote quote(PriceQuery query)
            throws InvalidQuantityException, PricingUnavailableException;
}
~~~

Mục tiêu là cho client mới dùng PricingUseCase nhưng các client cũ đã biên dịch vẫn gọi được LegacyPriceApi.quote(String, int).

### 4.1. Adapter giữ nguyên chữ ký public

Một lớp trung gian có thể triển khai như sau:

~~~java
package com.example.pricing.legacy;

import com.example.pricing.application.PriceQuery;
import com.example.pricing.application.PriceQuote;
import com.example.pricing.application.PricingUseCase;
import com.example.pricing.application.InvalidQuantityException;
import com.example.pricing.application.PricingUnavailableException;
import java.util.Objects;

public class LegacyPriceApi {
    private final PricingUseCase delegate;

    // Giữ constructor public không tham số đã phát hành.
    public LegacyPriceApi() {
        this(LegacyPricingComposition.createUseCase());
    }

    // Constructor bổ sung giúp kiểm thử và cấu hình tường minh.
    public LegacyPriceApi(PricingUseCase delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    /**
     * @deprecated New code should use PricingUseCase directly.
     */
    @Deprecated(since = "2.0")
    public int quote(String sku, int quantity)
            throws LegacyPricingException {
        try {
            PriceQuote result =
                    delegate.quote(new PriceQuery(sku, quantity));
            return Math.toIntExact(result.amountInMinorUnits());
        } catch (InvalidQuantityException e) {
            throw LegacyPricingException.invalidInput(e);
        } catch (PricingUnavailableException e) {
            throw LegacyPricingException.temporarilyUnavailable(e);
        } catch (ArithmeticException e) {
            throw LegacyPricingException.amountOutOfRange(e);
        }
    }
}
~~~

Ở ví dụ này, LegacyPricingComposition là điểm tạo service phù hợp với cấu hình ứng dụng. LegacyPricingException giả định có các factory method chuyển lỗi theo hợp đồng đã công bố. Đây là tên minh họa; trong dự án thực tế cần dùng constructor, error code và logic xử lý tương ứng với API cũ.

Các quyết định quan trọng trong adapter:

1. Giữ nguyên package, tên class và loại class.
2. Giữ constructor public không tham số nếu client cũ từng gọi.
3. Giữ method instance tên quote, kiểu tham số String/int và kiểu trả về int.
4. Không đổi method thành static hoặc đổi class thành interface chỉ để phù hợp thiết kế mới.
5. Dữ liệu được chuyển sang PriceQuery ở ranh giới adapter.
6. Kết quả long được đổi về int bằng Math.toIntExact để không âm thầm tràn số.
7. Exception của use case được ánh xạ về các dạng lỗi legacy mà client cũ có thể hiểu.
8. Client mới phụ thuộc trực tiếp vào PricingUseCase nên không phải mang tên LegacyPriceApi vào phần lõi.

Trong thực tế, nếu API cũ có quy tắc xử lý giá vượt giới hạn khác với ví dụ, adapter phải dùng đúng quy tắc đó. Math.toIntExact là một biện pháp phát hiện tràn số, không tự chứng minh tương thích hành vi với hệ thống cũ.

### 4.2. Vì sao không giữ cùng tên method và đổi thành static?

Client được biên dịch với instance method thường chứa chỉ dẫn invokevirtual. Nếu phiên bản mới chỉ cung cấp static method cùng tên và descriptor, JVM có thể ném IncompatibleClassChangeError khi lời gọi được phân giải. Chiều ngược lại cũng có thể gây lỗi.

Không thể khai báo đồng thời một static method và một instance method cùng tên, cùng danh sách tham số trong một class Java chỉ để đáp ứng cả hai kiểu gọi. Nếu muốn chuyển từ static utility sang instance service, nên giữ static facade cũ và đặt instance API mới trong một kiểu khác.

Tương tự, khi muốn chuyển một class public thành interface, nên giữ class cũ và bổ sung interface với tên nhị phân mới. Đổi trực tiếp cùng fully qualified name từ class sang interface có thể phá binary client cũ dùng new, extends hoặc invokevirtual.

### 4.3. Chuyển đổi DTO theo ý nghĩa nghiệp vụ

Mapper không đơn thuần chép field có tên tương tự. Các trường phải được chuyển theo đơn vị và ý nghĩa.

| Dữ liệu legacy | Dữ liệu mới | Điều cần bảo toàn |
|---|---|---|
| totalCents kiểu int | amountInMinorUnits kiểu long | Đơn vị tiền tệ và quy tắc xử lý vượt phạm vi int. |
| createdAt là chuỗi local time | Instant hoặc OffsetDateTime | Múi giờ, offset, format và hành vi với dữ liệu lịch sử. |
| status là chuỗi OPEN/DONE | Enum với nhiều trạng thái hơn | Mapping cho trạng thái mới mà client cũ không biết. |
| null nghĩa là không tìm thấy | Optional.empty() hoặc NotFoundException | Hình thức phản hồi mà client cũ mong đợi. |
| ID số nguyên | UUID hoặc định danh domain | Tính ổn định, round-trip và không mất dữ liệu. |
| Danh sách có thứ tự cũ | Collection không bảo đảm thứ tự | Thứ tự và tính ổn định nếu consumer dựa vào nó. |

Nếu mô hình mới cho phép nhiều trạng thái hơn, cần có chính sách ánh xạ khi client cũ không diễn đạt được trạng thái mới. Tránh âm thầm đổi mọi trạng thái lạ thành DONE hoặc bỏ qua trường quan trọng; phải quyết định và tài liệu hóa rõ cách biểu diễn hoặc trả lỗi phù hợp.

## 5. Thiết kế adapter cho HTTP API và message

Hợp đồng Java binary không phải ranh giới duy nhất. Khi migration từ Servlet sang framework/web stack mới, thay JSON library hoặc đổi domain model, HTTP API và message schema cũng có thể cần lớp tương thích.

### 5.1. Giữ HTTP endpoint v1

Giả sử client cũ gọi:

~~~http
GET /api/v1/orders/ORD-100
Accept: application/json
~~~

Response đã công bố:

~~~json
{
  "orderId": "ORD-100",
  "totalCents": 12500,
  "status": "OPEN"
}
~~~

Ứng dụng mới có thể lưu số tiền dưới dạng Money và trạng thái domain phong phú hơn. Thay vì sửa response v1 theo DTO mới, nên giữ controller/route v1 và dùng mapper:

~~~text
GET /api/v1/orders/{id}
       │
       ▼
V1 HTTP Controller
       │
       ▼
OrderV1Adapter / DTO Mapper
       │
       ▼
OrderQueryUseCase
       │
       ▼
Domain Order
       │
       ▼
OrderV1Response giữ schema cũ
~~~

Endpoint v2 có thể dùng DTO khác, nhưng v1 cần duy trì tên field, kiểu JSON, mã HTTP, format ngày và error contract của v1 theo chính sách tương thích.

Ví dụ adapter có thể chuyển domain NotFound thành HTTP 404 với JSON error code v1; lỗi validation thành HTTP 400 với body cũ; lỗi hạ tầng thành HTTP 503 nếu đúng hợp đồng. Không nên trả về stack trace hoặc exception Java mới cho client v1.

### 5.2. Message và event schema

Đối với Kafka, AMQP hoặc hàng đợi khác, adapter có thể giữ event cũ trong khi domain nội bộ thay đổi:

~~~text
Domain Event mới
     │
     ▼
Event Compatibility Mapper
     ├── Event v1 gửi cho consumer cũ
     └── Event v2 gửi cho consumer mới
~~~

Phải xác định chính sách versioning, tên topic/queue, schema registry, khóa phân vùng, thứ tự event, retry và idempotency. Nếu cùng một sự kiện nghiệp vụ được phát dưới hai version, cần tránh để consumer đăng ký cả hai rồi thực hiện nghiệp vụ hai lần.

Một kế hoạch migration có thể ưu tiên nâng consumer trước để đọc được schema mới, rồi mới thay producer. Ở hệ thống khác, việc phát song song v1/v2 là phù hợp. Quyết định phụ thuộc hợp đồng giao tiếp và khả năng kiểm soát consumer, không nên mặc định dual-publish luôn an toàn.

### 5.3. Serialization Java cần được xem xét riêng

Nếu client trao đổi object qua Java serialization, giữ tên class và method public vẫn chưa đủ. Thay field, class hierarchy hoặc serialVersionUID có thể làm dữ liệu đã lưu hoặc payload cũ không đọc được.

Adapter DTO dạng JSON không tự giải quyết lỗi Java serialization. Khi hệ thống còn dữ liệu nhị phân cũ, cần kế hoạch đọc/chuyển dữ liệu, kiểm tra serialVersionUID và phiên bản class thực tế, đồng thời chạy test deserialization với dữ liệu được tạo bởi phiên bản cũ.

## 6. Chuyển lỗi và bảo toàn ngữ nghĩa

Lỗi là một phần của hợp đồng. Adapter nên dịch exception hoặc result mới thành hình thức legacy đã cam kết.

Ví dụ:

| Kết quả từ lõi mới | Hợp đồng cũ có thể yêu cầu | Quy tắc adapter |
|---|---|---|
| Validation failure | LegacyValidationException hoặc mã lỗi INVALID_INPUT | Chuyển đúng loại lỗi và định dạng message/code. |
| Không tìm thấy | null, Optional hoặc exception riêng | Giữ hành vi đã công bố thay vì tự ý đổi. |
| Service unavailable | LegacyServiceException với trạng thái có thể retry | Bảo toàn phân loại transient/permanent. |
| Conflict | Error code ALREADY_EXISTS | Tránh đổi thành lỗi chung làm client retry sai. |
| Timeout | Timeout exception hoặc HTTP 504 theo API | Giữ ý nghĩa retry và không làm mất ngữ cảnh. |
| Result thành công | DTO hoặc response cũ | Giữ đơn vị, thứ tự, giá trị mặc định và format. |

Không nên bắt tất cả RuntimeException rồi trả về một kết quả thành công mặc định. Cách đó có thể giấu lỗi nghiệp vụ, phá monitoring và khiến client nghĩ rằng thao tác ghi dữ liệu đã thành công.

Mặt khác, để mặc exception mới xuyên qua adapter cũng không an toàn khi client chỉ xử lý loại lỗi cũ. Cần dịch những lỗi dự kiến ở ranh giới, đồng thời giữ nguyên cause và thông tin chẩn đoán phù hợp ở log nội bộ.

### 6.1. Checked exception, null và empty

Trong Java, danh sách checked exception là một phần của trải nghiệm source API, dù không nằm trong method descriptor theo cùng cách với tham số/giá trị trả về. Giữ method signature được client mong đợi giúp các module cũ biên dịch lại thuận lợi hơn.

Phải định nghĩa rõ:

- null có hợp lệ ở đầu vào không?
- null, Optional.empty(), danh sách rỗng hay exception đại diện cho “không có dữ liệu”?
- Exception nào có thể retry và exception nào là lỗi validation vĩnh viễn?
- Error code và HTTP status có ổn định không?
- Message lỗi có được consumer phân tích bằng chuỗi không?

Nếu client dựa vào message text, việc đổi text cũng có thể gây lỗi thực tế, dù đó không phải cách thiết kế client được khuyến khích. Khi có thể, xác định error code ổn định và tiến hóa để consumer không phụ thuộc message tự do.

### 6.2. Transaction và tính nguyên tử

Giả sử API cũ thực hiện tạo đơn hàng và trừ tồn kho trong một transaction. Adapter chỉ gọi hai use case mới liên tiếp mà không giữ transaction boundary có thể làm một bước thành công, một bước thất bại và để lại dữ liệu sai.

Vì vậy, trước khi tách service cần xác định:

- Transaction boundary thuộc use case nào?
- Có cần atomic commit hay phải dùng saga/compensation?
- Exception nào kích hoạt rollback?
- Retry có thể thực hiện hai lần một thao tác ghi không?
- Idempotency key có được giữ nguyên qua adapter không?

Adapter nên chuyển lời gọi và chính sách tương thích; tính đúng đắn của nghiệp vụ và transaction phải có chủ sở hữu rõ ràng trong application service hoặc tầng orchestration thích hợp.

## 7. Tránh biến lớp trung gian thành “hệ thống thứ hai”

Một adapter dễ bị phình to nếu nhóm đặt logic nghiệp vụ mới vào đó để sửa nhanh từng tình huống.

Các dấu hiệu cần xem xét:

- Adapter chứa nhiều quy tắc tính giá, phân quyền hoặc xử lý trạng thái nghiệp vụ thay cho domain.
- Cùng một quy tắc được cài trong adapter v1 và controller v2.
- Adapter biết quá nhiều chi tiết persistence hoặc gọi trực tiếp database.
- Các service mới import class legacy để tránh viết mapper.
- Có nhiều vòng chuyển DTO cũ → DTO mới → DTO cũ mà không có lý do.
- Tên API v1 tồn tại bên trong domain làm việc loại bỏ v1 trở nên khó khăn.

Nên giữ adapter mỏng theo nghĩa trách nhiệm rõ: parse/validate theo contract cũ, map dữ liệu, gọi use case, map kết quả và lỗi. “Mỏng” không có nghĩa ít dòng code bằng mọi giá; mapping phức tạp là hợp lý khi bảo toàn hợp đồng cũ thực sự cần thiết.

### 7.1. Điểm tạo dependency

Nếu API cũ từng cung cấp constructor không tham số, adapter có thể phải giữ nó. Tuy nhiên, không nên dùng một biến toàn cục có thể thay đổi tùy ý để cấp dependency nếu điều đó làm test và runtime khó dự đoán.

Một cách tổ chức là:

1. Giữ constructor cũ để bảo toàn binary/source API.
2. Constructor cũ chuyển đến composition root có quy tắc tạo service rõ ràng.
3. Bổ sung constructor nhận dependency để test và các client mới tự cấu hình.
4. Có lifecycle và cơ chế đóng resource nếu service tạo thread, connection hoặc scheduler.

Nếu service mới phụ thuộc vào transaction manager hay DI container, composition root phải được xác định theo cách vận hành ứng dụng. Không nên tạo một application context mới cho mỗi lời gọi legacy, vì chi phí và lifecycle có thể khác hoàn toàn với implementation cũ.

## 8. Kiểm chứng lớp tương thích

Test một adapter cần nhiều góc nhìn vì có thể giữ được behavior cho source mới nhưng phá binary client cũ.

### 8.1. API shape và binary compatibility

Với thư viện Java đã phát hành:

1. Lưu artifact thư viện phiên bản cũ.
2. Biên dịch một fixture client dựa trên phiên bản cũ.
3. Giữ nguyên class file client; không biên dịch lại.
4. Chạy fixture cũ với thư viện mới có adapter.
5. Thực thi các constructor, method, field và hierarchy mà client dùng.
6. Ghi lại linkage error, kết quả và hành vi.

Ví dụ chạy binary fixture trên Linux/macOS:

~~~bash
java -cp "client-old.jar:library-new.jar" com.example.compat.ClientFixture
~~~

Trên Windows:

~~~powershell
java -cp "client-old.jar;library-new.jar" com.example.compat.ClientFixture
~~~

Nếu cần so sánh API, có thể dùng javap để xem method descriptor, modifier và kiểu class/interface:

~~~bash
javap -classpath library-old.jar -p -s com.example.pricing.legacy.LegacyPriceApi
javap -classpath library-new.jar -p -s com.example.pricing.legacy.LegacyPriceApi
~~~

Công cụ như japicmp hoặc Revapi có thể tự động báo các thay đổi API giữa hai artifact. Tuy nhiên, kết quả so sánh metadata và test client cũ nên bổ sung cho nhau. Test binary xác nhận đường lời gọi thực thi, còn công cụ diff giúp phát hiện phạm vi API rộng hơn.

### 8.2. Contract tests cho hành vi cũ

Adapter nên được kiểm tra với một bộ test hợp đồng cụ thể:

| Nhóm test | Tình huống cần kiểm tra |
|---|---|
| Happy path | Dữ liệu legacy hợp lệ được map chính xác và trả kết quả đúng loại/đơn vị. |
| Boundary values | Giá trị 0, âm, cực đại, overflow, chuỗi rỗng, số lượng lớn. |
| Null/empty | Phân biệt null, empty collection, Optional và đối tượng thiếu field. |
| Errors | Mỗi loại lỗi mới được chuyển đúng exception/error code/status cũ. |
| Date/time | Offset, timezone, daylight saving, dữ liệu lịch sử và format cũ. |
| Concurrency | Thread-safety, gọi đồng thời và trạng thái dùng chung. |
| Write semantics | Idempotency, retry, transaction và rollback khi lỗi một phần. |
| Compatibility | Chạy lại fixture đã biên dịch với version cũ. |

Khi có dữ liệu response v1 đã công bố, có thể dùng golden fixtures để so sánh JSON hoặc serialized payload. Với JSON, nên kiểm tra semantic contract (field, type, value, error shape) và chỉ so sánh thứ tự field nếu thứ tự đó thực sự nằm trong hợp đồng.

### 8.3. Test với framework và môi trường thực tế

Nếu migration thay Spring Framework, Spring Boot, Jakarta namespace, serializer hoặc HTTP stack, cần kiểm thử adapter qua đúng entry point được triển khai.

Ví dụ, một unit test chỉ gọi LegacyOrderAdapter trực tiếp chưa chứng minh endpoint v1 hoạt động: controller mapping, validation, security filter, content negotiation hoặc exception handler có thể đã thay đổi. Cần có integration test gửi request thật qua web stack và xác nhận response theo hợp đồng cũ.

Nếu thư viện được đóng gói trong executable JAR hoặc container, kiểm tra artifact runtime thực tế và dependency graph. Một adapter đúng source vẫn có thể không hoạt động nếu deployment nạp một bản JAR cũ khác với artifact vừa build.

## 9. Theo dõi mức sử dụng legacy API

Adapter là vị trí thuận tiện để biết còn bao nhiêu client sử dụng hợp đồng cũ. Mỗi lời gọi có thể ghi metric hoặc structured log có giới hạn dữ liệu nhạy cảm.

Những chỉ số hữu ích:

- Số lượng request hoặc invocation theo API version và operation.
- Tỷ lệ lỗi, timeout và kết quả mapping không hỗ trợ.
- Latency của adapter và của use case phía sau.
- Nhóm consumer hoặc client version nếu có định danh đáng tin cậy.
- Tỷ lệ lưu lượng còn lại trên API v1 so với v2.
- Số lượng ngoại lệ tương thích còn mở và thời hạn xử lý.

Không nên log toàn bộ request body hoặc token chỉ để đếm số client cũ. Ưu tiên metric tổng hợp, ID đã được cho phép và nhãn có cardinality phù hợp. Không phát sinh side effect nghiệp vụ từ việc đo đạc.

### 9.1. Quan sát mà không làm thay đổi hành vi

Tăng metric, tracing hoặc log phải không làm API cũ thay đổi timeout, exception hoặc latency quá mức. Nếu hệ thống giám sát tạm thời không hoạt động, không nên để phần đo đạc không thiết yếu làm request nghiệp vụ thất bại, trừ khi có yêu cầu vận hành cụ thể.

Đối với adapter có mapping không thể biểu diễn trong schema cũ, nên có metric/cảnh báo riêng để nhóm biết cần nâng client hoặc điều chỉnh chính sách trước khi các trường hợp này xuất hiện nhiều trong production.

## 10. Lộ trình chuyển đổi theo giai đoạn

Một cách tiến hóa API thường dùng:

~~~text
Giai đoạn A: Baseline hợp đồng cũ
      │
      ▼
Giai đoạn B: Đặt adapter/facade trước lõi mới
      │
      ▼
Giai đoạn C: Chạy client cũ và client mới song song
      │
      ▼
Giai đoạn D: Di chuyển consumer, đo usage và giảm phụ thuộc
      │
      ▼
Giai đoạn E: Xác nhận không còn consumer cần hợp đồng cũ
      │
      ▼
Giai đoạn F: Loại bỏ legacy API ở phiên bản phát hành phù hợp
~~~

### Giai đoạn A — Khóa baseline

Lưu artifact/version cũ, hợp đồng public, fixture request/response, binary fixture và danh sách consumer. Chụp baseline về kết quả, lỗi, latency và những hành vi quan trọng. Nếu không có baseline, rất khó chứng minh adapter giữ được hợp đồng đã tồn tại.

### Giai đoạn B — Thêm adapter

Thêm facade hoặc adapter ở đúng biên, để lõi mới có API rõ ràng. Giữ class/method/endpoint cũ theo cam kết. Tạo mapper, exception policy và test riêng cho biên tương thích. Trong giai đoạn này, client cũ chưa bắt buộc đổi mã nguồn.

### Giai đoạn C — Triển khai song song

Cho consumer đã nâng dùng API mới. Consumer chưa nâng tiếp tục qua API cũ. Nếu thao tác có side effect, không nên gọi đồng thời hai implementation cho cùng một request chỉ để so sánh kết quả; cần cách quan sát an toàn hoặc môi trường thử nghiệm riêng.

### Giai đoạn D — Di chuyển và đo lường

Công bố API thay thế và hướng dẫn migration, xác định owner cho từng consumer, xử lý trường hợp ánh xạ chưa thể hiện đủ dữ liệu. Dùng metric/trace phù hợp để xác minh lưu lượng v1 giảm xuống.

### Giai đoạn E — Chốt điều kiện bỏ adapter

Không chỉ dựa trên “không thấy request trong vài giờ”. Cần kiểm tra consumer chạy theo lịch tháng/quý, batch job, plugin ít dùng và các client ngoài phạm vi quan sát. Ghi rõ thời gian quan sát, mốc ngừng hỗ trợ và quy trình xử lý consumer chưa nâng.

### Giai đoạn F — Phát hành breaking change có kiểm soát

Chỉ loại bỏ API cũ khi phù hợp chính sách versioning và cam kết hỗ trợ. Nếu cần breaking binary compatibility, phải truyền thông rõ major version/artifact mới, migration guide và yêu cầu biên dịch lại client. SemVer có thể giúp truyền đạt mức thay đổi nhưng không làm binary cũ tự tương thích.

## 11. Quản lý version, deprecation và tài liệu migration

API cũ có thể được đánh dấu Deprecated để thông báo hướng di chuyển:

~~~java
/**
 * @deprecated Migrate to PricingUseCase.
 */
@Deprecated(since = "2.0")
public int quote(String sku, int quantity)
        throws LegacyPricingException {
    // Delegate to new use case.
}
~~~

Thuộc tính forRemoval chỉ nên được dùng khi có kế hoạch loại bỏ rõ ràng. Nó là tín hiệu cho người dùng và tooling rằng API được dự định xóa ở phiên bản sau; không phải cơ chế tự động chuyển lời gọi sang API mới.

Một migration guide nên chỉ rõ:

- API cũ, API mới và mapping tương ứng.
- Cách khởi tạo hoặc inject dependency thay cho cơ chế cũ.
- Khác biệt về DTO, kiểu thời gian, đơn vị tiền, error code và transaction.
- Cách chuyển consumer đồng bộ và consumer chạy nền.
- Phiên bản bắt đầu deprecated, phiên bản dự kiến ngừng hỗ trợ.
- Điều kiện tương thích nhị phân và yêu cầu rebuild nếu có breaking change.
- Các test/example tối thiểu để consumer xác nhận việc di chuyển.

Nếu package cũ phải giữ lại vì binary contract, không nên tự động di chuyển nó sang một package mới mà không cung cấp kiểu bridge tương ứng. Fully qualified name là một phần của identity mà client bytecode sử dụng.

## 12. Rollback và chiến lược khi adapter gặp lỗi

Thêm lớp trung gian có thể đưa vào rủi ro mới: mapping sai dữ liệu, đổi exception, tăng latency hoặc sai transaction. Kế hoạch rollout cần dự tính cách quay lại.

Các câu hỏi nên trả lời trước khi triển khai:

1. Có thể quay lại artifact cũ nếu adapter lỗi không?
2. Dữ liệu mà lõi mới đã ghi có còn được phiên bản cũ đọc hiểu không?
3. Event v2 đã phát có thể ảnh hưởng đến consumer v1 như thế nào?
4. Cần tắt route v2 hoặc chuyển traffic về v1 bằng cơ chế nào?
5. Có migration database hoặc state change không thể đảo ngược không?
6. Những metric và alarm nào cho biết adapter đang tạo kết quả khác hợp đồng?

Rollback code không đồng nghĩa với rollback dữ liệu. Nếu mô hình mới ghi dữ liệu ở dạng mà implementation cũ không đọc được, phải thiết kế giai đoạn chuyển tiếp schema hoặc rollback strategy riêng. Adapter cấp API chỉ giải quyết giao diện, không tự bảo đảm tương thích dữ liệu bền vững.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách tiếp cận phù hợp |
|---|---|---|
| Đổi static thành instance ngay trên method public cũ. | Client binary cũ có thể gặp IncompatibleClassChangeError. | Giữ static facade cũ, thêm service instance với kiểu mới. |
| Đổi class public thành interface cùng fully qualified name. | Client dùng new, extends hoặc invokevirtual có thể không liên kết được. | Giữ class cũ; giới thiệu interface mới, cho class cũ implements interface. |
| Giữ method name nhưng đổi kiểu trả về/tham số. | Method descriptor thay đổi; có thể phát sinh NoSuchMethodError. | Giữ method cũ và bổ sung overload/API mới với tên khác khi cần. |
| Map long sang int bằng cast trực tiếp. | Tràn số âm thầm và trả giá trị không đúng. | Kiểm tra giới hạn, quyết định cách báo lỗi tương thích. |
| Đổi null thành exception hoặc đổi exception thành null. | Client xử lý lỗi sai hoặc bị NullPointerException. | Bảo toàn chính sách legacy theo từng method. |
| Cho DTO legacy đi xuyên vào domain mới. | Lõi mới bị phụ thuộc ngược vào phiên bản API cũ. | Map ở ranh giới adapter. |
| Copy toàn bộ nghiệp vụ vào adapter v1. | Hai nguồn logic dễ lệch nhau, khó gỡ adapter. | Dùng chung application service/use case. |
| Bỏ qua retry/idempotency khi chuyển sang HTTP hoặc messaging. | Có thể xử lý lặp, mất transaction hoặc lệch dữ liệu. | Thiết kế policy đúng theo nghiệp vụ ở tầng thích hợp. |
| Chỉ test source mới, không chạy client đã biên dịch cũ. | Không phát hiện binary incompatibility. | Giữ binary fixture, test runtime với thư viện mới. |
| Xóa adapter khi traffic hiện tại bằng 0. | Batch job/consumer ít chạy vẫn có thể dùng API cũ. | Theo dõi chu kỳ sử dụng và xác nhận danh sách consumer. |

## 14. Quy trình thiết kế cho một thay đổi API cụ thể

Khi nhận yêu cầu thay implementation trong quá trình migration, có thể làm theo trình tự:

1. **Xác định ranh giới:** API Java public, HTTP endpoint, event hay cả ba? Ai sử dụng?
2. **Ghi baseline:** lưu signature, binary artifact, sample request/response, error behavior và test.
3. **Liệt kê khác biệt:** DTO, field, error, lifecycle, transaction, static/instance, class/interface, serializer và version framework.
4. **Chọn dạng trung gian:** facade giữ entry point cũ, adapter/map vào use case mới, mapping lỗi và version transport nếu cần.
5. **Thiết kế hướng dependency:** phần lõi mới không cần biết legacy DTO hoặc exception.
6. **Định nghĩa chính sách không biểu diễn được:** overflow, enum lạ, timezone thiếu, operation mới không có bản dịch v1.
7. **Triển khai adapter:** giữ hợp đồng public cần bảo toàn, tập trung mapping và delegation.
8. **Chạy kiểm chứng:** client binary cũ, source client cũ, contract test và integration test qua runtime thực tế.
9. **Đo và triển khai:** quan sát usage, lỗi mapping, latency, rollback conditions.
10. **Lên kế hoạch loại bỏ:** deprecation, migration guide, owner consumer, thời hạn và điều kiện chấm dứt hỗ trợ.

Kết quả của giai đoạn thiết kế nên có sơ đồ ranh giới, danh sách hợp đồng được bảo toàn, bảng mapping, quy tắc xử lý lỗi, quyết định versioning, kết quả kiểm chứng và điều kiện rollback/loại bỏ. Đây là cơ sở để người review hiểu chính xác adapter bảo vệ điều gì và những khác biệt nào đã được chấp nhận.

## 15. Kết luận

Adapter và lớp trung gian giúp API tiến hóa mà không buộc mọi consumer đổi cùng lúc. Chúng giữ hợp đồng cũ ở ranh giới đã phát hành, chuyển lời gọi và dữ liệu sang phần lõi mới, đồng thời cô lập exception, DTO, giao thức và giả định của hệ thống cũ.

Giá trị của giải pháp phụ thuộc vào tính chính xác của hợp đồng được giữ lại: tên nhị phân, constructor, static/instance, class/interface, method descriptor, response schema, error behavior, transaction và các cam kết vận hành. Một adapter tốt có điểm vào ổn định, logic mapping có chủ sở hữu rõ ràng, test với binary và dữ liệu cũ, khả năng quan sát mức sử dụng và kế hoạch loại bỏ theo phiên bản. Nhờ vậy, migration JDK/framework/dependency có thể tiến hành từng bước trong khi các client chưa nâng cấp vẫn tiếp tục làm việc theo hợp đồng đã công bố.
