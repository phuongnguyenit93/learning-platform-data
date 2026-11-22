# Thiết kế khóa bộ nhớ đệm theo đúng ngữ cảnh và dữ liệu trong AOP

## 1. Vấn đề: kết quả giống nhau chỉ khi các điều kiện tạo kết quả giống nhau

Bộ nhớ đệm (cache) giúp trả lại kết quả đã tính thay vì thực hiện lại một phép tính hoặc truy vấn tốn kém. Khi dùng Aspect-Oriented Programming (AOP), một *around advice* có thể chặn lời gọi phương thức, tìm giá trị đã lưu, trả ngay khi có cache hit hoặc gọi phương thức gốc rồi lưu kết quả khi cache miss.

Điểm khó không nằm ở phép tra cứu cache mà ở câu hỏi: **hai lời gọi nào được phép dùng chung một kết quả?** Nếu thiết kế khóa sai, cache có thể trả kết quả cũ, sai phiên bản, sai người dùng hoặc thậm chí làm lộ dữ liệu giữa những phạm vi truy cập khác nhau.

Ví dụ một phép tính báo giá:

- Cùng mã sản phẩm và tiền tệ, cùng bảng giá, cùng tenant và nhóm khách hàng: có thể dùng chung kết quả.
- Cùng mã sản phẩm nhưng tenant khác: có thể áp dụng bảng giá hoặc dữ liệu riêng.
- Cùng tenant nhưng quyền xem giá hoặc nhóm khách hàng khác: kết quả có thể khác.
- Cùng đầu vào nhưng phiên bản chính sách hoặc bảng giá thay đổi: cần phân biệt dữ liệu cũ và mới.
- Chuỗi mã sản phẩm có khoảng trắng/thường-hoa khác nhau: chỉ được coi như một giá trị nếu **quy tắc nghiệp vụ** xác nhận chúng tương đương.

Do đó, một khóa cache đúng phải mô tả **toàn bộ những yếu tố có thể ảnh hưởng đến kết quả**, theo hợp đồng của lời gọi được cache.

## 2. Khái niệm AOP cần dùng

- **Join point:** vị trí thực thi mà cơ chế AOP có thể quan sát hoặc can thiệp; ở bài này là ranh giới gọi một phương thức có thể cache.
- **Pointcut:** quy tắc chọn các join point đủ điều kiện dùng chính sách cache.
- **Advice:** logic chạy quanh lời gọi, kiểm tra cache, gọi phương thức gốc khi miss và ghi kết quả.
- **Aspect:** tập hợp pointcut và advice phục vụ cùng một chính sách xuyên suốt.
- **Weaving/interception:** cách liên kết aspect vào chương trình; tùy cơ chế cụ thể mà một số lời gọi nội bộ hoặc điểm thực thi có thể không đi qua advice.

Cache là **chính sách thực thi**: nó thay đổi việc có cần tính lại kết quả hay không, nhưng về nguyên tắc không được làm thay đổi ý nghĩa kết quả mà người gọi được phép nhận.

Một luồng *around advice* đồng bộ cơ bản:

~~~text
caller -> pointcut phù hợp -> cache advice
                                |
                      tạo khóa từ ngữ cảnh
                      và đầu vào đã chuẩn hóa
                                |
                         tra cứu cache
                          /          \
                       HIT            MISS
                        |               |
                 trả giá trị          proceed()
                                        |
                                   tính thành công?
                                     /      \
                                    có      không
                                    |        |
                                lưu cache  truyền lỗi
                                    |
                                trả kết quả
~~~

Đây là sơ đồ khái niệm, không có nghĩa mọi phương thức hay mọi giá trị đều nên được cache. Việc lưu kết quả lỗi, kết quả rỗng, huỷ tác vụ hoặc phản hồi từ hệ thống ngoài phải có chính sách riêng.

## 3. Mô hình khóa: phụ thuộc vào những gì?

Giả sử phương thức logic là:

~~~text
quote(context, productCode, currency) -> price
~~~

Một kết quả có thể phụ thuộc vào:

| Thành phần | Có thể ảnh hưởng kết quả như thế nào? | Cách đưa vào khóa |
| --- | --- | --- |
| Danh tính thao tác | Hai phương thức khác nhau có thể nhận cùng tham số nhưng trả loại dữ liệu khác | Namespace/operation cố định, như quote:v1 |
| Tenant hoặc vùng dữ liệu | Cùng ID sản phẩm nhưng ở kho dữ liệu khác | Tenant ID ổn định lấy từ ngữ cảnh đáng tin |
| Quyền hoặc nhóm giá | Người mua thường và VIP có giá khác | Nhóm quyền/giá đã tính từ chính sách hoặc dấu vân tay quyền |
| Đầu vào nghiệp vụ | SKU, số lượng, tiền tệ, bộ lọc, phân trang | Biểu diễn chuẩn hóa của **mọi** tham số liên quan |
| Phiên bản dữ liệu | Bảng giá, snapshot, cấu hình đã đổi | Version/revision đáng tin, hoặc invalidation khi thay đổi |
| Locale/múi giờ | Chuỗi hiển thị, lịch và phân đoạn ngày có thể khác | Locale/zone khi chúng thực sự ảnh hưởng kết quả |
| Feature flag hoặc thuật toán | Cùng dữ liệu nhưng nhánh xử lý/giải thuật khác | Phiên bản chính sách, flag hoặc namespace mới |
| Phạm vi quyền nhìn thấy | Một tập dữ liệu được lọc theo tài khoản | Phạm vi truy cập hoặc tài khoản, khi cache phân quyền |

Không cần đưa **mọi thông tin sẵn có** vào khóa: điều này làm giảm cache hit mà không tăng tính đúng. Ngược lại, thiếu một yếu tố có tác động đến kết quả là lỗi nghiêm trọng.

Một cách kiểm tra tính đúng:

> Nếu hai lời gọi có cùng khóa K, liệu kết quả dùng chung có đúng với **cả hai lời gọi** theo hợp đồng nghiệp vụ và an toàn truy cập không?

Viết dưới dạng bất biến:

~~~text
key(a) == key(b)
    => reusableResult(a, b) == true
~~~

Chiều ngược lại không bắt buộc: hai lời gọi khác khóa vẫn có thể tình cờ trả cùng giá trị; chúng chỉ không bị buộc phải dùng chung bản cache. Không đánh đồng “giá trị kết quả trùng nhau” với “có quyền chia sẻ bản cache”.

## 4. Tách ngữ cảnh nghiệp vụ, dữ liệu đầu vào và trạng thái thực thi

### 4.1. Ngữ cảnh ảnh hưởng kết quả

Ngữ cảnh (context) có thể nằm ngoài danh sách tham số của phương thức: tenant hiện tại, vai trò/quyền, địa bàn, phiên bản bảng giá, locale, múi giờ, cấu hình tính giá. Advice chỉ nhìn thấy được những gì được đưa tới join point hoặc được cung cấp qua cơ chế ngữ cảnh được thiết kế rõ ràng.

Ví dụ một phương thức chỉ nhận mã sản phẩm nhưng bên trong sử dụng tenant và nhóm giá của yêu cầu hiện tại. Nếu advice tạo khóa chỉ từ mã sản phẩm, hai yêu cầu của hai tenant có thể va vào cùng một bản cache dù nhận kết quả khác nhau.

**Giải pháp ưu tiên:** biểu diễn các yếu tố ảnh hưởng kết quả thành ngữ cảnh bất biến, có tên và được truyền rõ cho phép tính; nếu dùng ngữ cảnh ngầm, xây dựng bộ trích xuất có hợp đồng và kiểm thử đầy đủ. Dữ liệu như tenant ID hoặc scope phân quyền phải xuất phát từ nguồn tin cậy phía hệ thống, không đơn giản chấp nhận giá trị tự khai từ client.

### 4.2. Ngữ cảnh không ảnh hưởng kết quả

Request ID, trace ID, timestamp ghi log, tên luồng hoặc IP ngẫu nhiên thường giúp quan sát và tương quan lời gọi, nhưng không quyết định kết quả của một phép tính thuần. Đưa chúng vào khóa làm mỗi lời gọi sinh một khóa khác nhau, khiến cache gần như vô dụng.

Ngoại lệ là khi *chính hợp đồng nghiệp vụ* dùng yếu tố ấy để tính toán. Chẳng hạn giá vé thực sự phụ thuộc thời điểm đặt, hoặc chính sách theo vùng địa lý dùng IP đã được chuẩn hóa đáng tin; khi đó cần mô hình hóa nó thành đầu vào nghiệp vụ hoặc mốc thời gian có nghĩa, không tùy tiện dùng thời điểm gọi System.currentTimeMillis().

### 4.3. Chuẩn hóa dữ liệu phải nhất quán với ngữ nghĩa

Hai cách viết " pen " và "PEN" có thể cùng chỉ một SKU nếu domain xác nhận bỏ khoảng trắng biên và không phân biệt chữ hoa/thường. Nhưng mã nhạy chữ hoa, token mã hóa, định danh người dùng hoặc đường dẫn tệp có thể không cho phép làm vậy.

Nguyên tắc:

1. Xác định các phép biến đổi hợp lệ trong domain trước khi xây khóa.
2. Chuẩn hóa **một lần** ở ranh giới đầu vào, dùng cùng dạng chuẩn cho cả khóa và tính toán.
3. Dùng Locale.ROOT khi chuẩn hóa mã kỹ thuật không phụ thuộc ngôn ngữ; với từ ngữ hiển thị cho người dùng, xử lý locale theo hợp đồng.
4. Phân biệt null, chuỗi rỗng và giá trị thiếu nếu chúng có ý nghĩa khác nhau.
5. Với số thập phân, ngày, múi giờ, enum và danh sách, xác định chính xác dạng biểu diễn và quy tắc tương đương.

Không được chỉ chuẩn hóa khóa trong khi vẫn gửi đầu vào gốc có ý nghĩa khác nhau vào phương thức: điều đó tạo hai lời gọi cùng khóa nhưng kết quả thực tế khác nhau.

## 5. Cách biểu diễn khóa an toàn

### 5.1. Khóa cấu trúc bất biến

Một khóa là **tuple bất biến có kiểu**, gồm namespace/schema version, tenant, scope, version dữ liệu và các tham số chuẩn hóa. Trong Java, record thích hợp để minh họa do tạo sẵn equals() và hashCode() theo thành phần.

~~~text
CacheKey(
  schemaVersion = 1,
  operation = "quote",
  tenantId = "ACME",
  priceTier = "VIP",
  priceListVersion = 7,
  sku = "PEN",
  currency = "VND"
)
~~~

Biểu diễn này tránh việc nối chuỗi thủ công kiểu "AC" + "ME" và "A" + "CME" có thể cho ra cùng chuỗi. Nếu phải chuyển tuple sang khóa chuỗi cho hệ thống lưu trữ ngoài, dùng encoding có độ dài trường/kiểu rõ ràng hoặc serialization canonical có phiên bản.

### 5.2. Tránh khóa dựa trên toString() hoặc hash đơn giản

- **Object.toString():** không có hợp đồng biểu diễn ổn định cho mọi lớp; có thể chứa địa chỉ/identity hay thông tin nội bộ.
- **Object.hashCode():** không đảm bảo duy nhất; va chạm hash có thể xảy ra, và hash không tự mang ý nghĩa phân vùng dữ liệu.
- **Nối chuỗi không escape:** có thể tạo va chạm giữa những tuple khác nhau, đặc biệt khi giá trị chứa dấu phân cách.
- **Serialization không chuẩn:** thứ tự thuộc tính của map, định dạng số và timezone có thể tạo nhiều khóa cho một dữ liệu logic hoặc gộp sai dữ liệu.
- **Giá trị mutable:** object/collection thay đổi sau khi làm khóa có thể phá equals/hashCode và gây lỗi tra cứu.

Nếu khóa là byte hoặc string canonical, nên có schema version. Hash mật mã có thể thu gọn một khóa dài, nhưng bản hash vẫn có xác suất va chạm, không tự giải quyết sai sót do thiếu thành phần và không nên dùng như cơ chế che giấu dữ liệu nhạy cảm.

### 5.3. Danh sách, tập hợp và map

Khóa từ tập hợp cần biết **thứ tự có ý nghĩa không**. Với danh sách ưu tiên, giữ thứ tự; với tập các nhãn lọc không quan tâm thứ tự, sắp xếp theo chuẩn domain trước khi serialize. Phải phân biệt phần tử trùng, null và các kiểu dữ liệu có thể có cùng biểu diễn chuỗi. Với map, xác định thứ tự key chuẩn và cách mã hóa cả khóa lẫn giá trị; không dựa vào thứ tự duyệt tình cờ của cấu trúc mutable.

## 6. Ví dụ Java 17 chạy độc lập: khóa đúng ngữ cảnh và dữ liệu

Chương trình dùng một decorator để minh họa hành vi *around advice*. Trong hệ thống AOP thực, pointcut và weaving có thể gắn cùng logic quanh phương thức; ở đây cách bọc tường minh giúp chương trình chạy không cần thư viện AOP. **Chính sách đúng đắn của khóa** là nội dung cần học, không phải cú pháp của một framework.

Báo giá phụ thuộc vào tenant, nhóm giá, phiên bản bảng giá, SKU và tiền tệ. Request chuẩn hóa SKU/tiền tệ ngay lúc xây dựng; khóa là record bất biến. Bộ đếm của dịch vụ gốc giúp phân biệt số lần gọi từ client với số lần tính toán thực sự.

Tạo tệp **ContextCacheDemo.java**:

~~~java
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ContextCacheDemo {
    record QuoteContext(String tenantId, String priceTier, int catalogVersion) {
        QuoteContext {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(priceTier);
            if (tenantId.isBlank()
                    || !(priceTier.equals("REGULAR") || priceTier.equals("VIP"))
                    || catalogVersion < 0) {
                throw new IllegalArgumentException("invalid context");
            }
        }
    }

    record QuoteRequest(String sku, String currency) {
        QuoteRequest {
            Objects.requireNonNull(sku);
            Objects.requireNonNull(currency);
            sku = sku.strip().toUpperCase(Locale.ROOT);
            currency = currency.strip().toUpperCase(Locale.ROOT);
            if (sku.isEmpty()
                    || !(currency.equals("VND") || currency.equals("USD"))) {
                throw new IllegalArgumentException("invalid request");
            }
        }
    }

    record CacheKey(
            int schemaVersion,
            String tenantId,
            String priceTier,
            int catalogVersion,
            String sku,
            String currency) {}

    interface QuoteService {
        int quote(QuoteContext context, QuoteRequest request);
    }

    static final class DomainQuoteService implements QuoteService {
        final AtomicInteger computations = new AtomicInteger();

        @Override
        public int quote(QuoteContext context, QuoteRequest request) {
            computations.incrementAndGet();
            int base = switch (request.sku()) {
                case "PEN" -> 100;
                case "BOOK" -> 200;
                default -> throw new IllegalArgumentException("unknown sku");
            };
            int tenantAdd = context.tenantId().equals("ACME") ? 0 : 500;
            int tierDiscount = context.priceTier().equals("VIP") ? 20 : 0;
            int amount = base + tenantAdd - tierDiscount
                    + context.catalogVersion();
            return request.currency().equals("VND") ? amount : amount / 20;
        }
    }

    // Decorator minh họa một around advice.
    static final class CachingAspect implements QuoteService {
        private final QuoteService target;
        private final ConcurrentHashMap<CacheKey, Integer> cache =
                new ConcurrentHashMap<>();

        CachingAspect(QuoteService target) {
            this.target = target;
        }

        @Override
        public int quote(QuoteContext context, QuoteRequest request) {
            CacheKey key = new CacheKey(
                    1, context.tenantId(), context.priceTier(),
                    context.catalogVersion(),
                    request.sku(), request.currency()
            );
            return cache.computeIfAbsent(
                    key, ignored -> target.quote(context, request));
        }
    }

    public static void main(String[] args) {
        DomainQuoteService origin = new DomainQuoteService();
        QuoteService service = new CachingAspect(origin);

        QuoteContext regular = new QuoteContext("ACME", "REGULAR", 1);
        System.out.println("first="
                + service.quote(regular, new QuoteRequest(" pen ", "vnd")));
        System.out.println("same="
                + service.quote(regular, new QuoteRequest("PEN", "VND")));
        System.out.println("vip="
                + service.quote(new QuoteContext("ACME", "VIP", 1),
                        new QuoteRequest("PEN", "VND")));
        System.out.println("tenant="
                + service.quote(new QuoteContext("BETA", "REGULAR", 1),
                        new QuoteRequest("PEN", "VND")));
        System.out.println("version="
                + service.quote(new QuoteContext("ACME", "REGULAR", 2),
                        new QuoteRequest("PEN", "VND")));
        System.out.println("computations=" + origin.computations.get());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 ContextCacheDemo.java
java ContextCacheDemo
~~~

Kết quả stdout xác định:

~~~text
first=101
same=101
vip=81
tenant=601
version=102
computations=4
~~~

**Diễn giải từng lời gọi:**

1. Lời gọi đầu với tenant ACME, REGULAR, catalogVersion=1 và SKU " pen " được chuẩn hóa thành "PEN": cache miss, tính 100 + 0 + 0 + 1 = 101.
2. Lời gọi thứ hai có cùng khóa sau chuẩn hóa: cache hit, kết quả vẫn 101 mà không tính lại.
3. Cùng SKU nhưng priceTier=VIP: khóa khác, giá 100 − 20 + 1 = 81.
4. Cùng SKU và nhóm REGULAR nhưng tenant=BETA: khóa khác, giá 100 + 500 + 1 = 601.
5. Cùng tenant và nhóm REGULAR nhưng catalogVersion=2: khóa khác, kết quả 102.
6. Có năm lần gọi qua wrapper nhưng chỉ **bốn lần** thực thi phương thức tính giá gốc.

Đây là ví dụ tính giá giả định để minh họa sự phụ thuộc, không phải quy tắc giá của một hệ thống thương mại thực. Thuộc tính catalogVersion phải do nguồn dữ liệu đáng tin quản lý; priceTier cũng cần được xác thực hoặc suy ra từ quyền/nhóm giá phía hệ thống. Không cho người dùng tự chọn context tùy ý rồi dùng nó như bằng chứng phân quyền.

### Vì sao dùng ConcurrentHashMap.computeIfAbsent()?

Với cùng một khóa, thao tác computeIfAbsent() giúp việc tìm và tạo entry nhất quán trong một ConcurrentHashMap. Hàm tính toán có thể chạy trong đường khóa/chồng chờ nội bộ, vì vậy nó nên ngắn, không thay đổi chính map và không gọi vòng lặp lại cùng key. Ví dụ chỉ tính toán bằng CPU đơn giản; với công việc chậm hoặc phụ thuộc mạng, cần cơ chế tải một lần theo khóa (*single-flight*), timeout và chính sách khi tải lỗi phù hợp.

Lỗi ném ra từ phép tính trong ví dụ **không được lưu** thành giá trị; ConcurrentHashMap cũng không hỗ trợ null làm giá trị cache. Nếu hợp đồng cần cache kết quả null, không-tìm-thấy hoặc lỗi, phải dùng kiểu biểu diễn kết quả rõ ràng và đặt TTL khác theo trường hợp. Ví dụ dùng map trong bộ nhớ, không có giới hạn số entry, TTL hoặc invalidation: đây là các yêu cầu quan trọng khi đưa vào vận hành.

## 7. Chọn điểm áp dụng AOP và hợp đồng cache

AOP giúp áp dụng cùng chính sách cho nhiều phương thức, nhưng pointcut phải đủ hẹp để chỉ chọn những thao tác có thể dùng lại kết quả. Trước khi gắn advice cần kiểm tra:

1. **Tính lặp lại:** cùng khóa ở thời gian còn hiệu lực có được phép trả cùng kết quả không?
2. **Không có tác dụng phụ cần lặp lại:** bỏ qua thực thi trên cache hit có làm mất ghi DB, audit bắt buộc, gửi message hoặc thay đổi trạng thái không?
3. **Hợp đồng lỗi:** exception, timeout, huỷ và null có cần cache không?
4. **Vòng đời dữ liệu:** bản ghi thay đổi lúc nào và được invalidation theo cơ chế nào?
5. **Giới hạn quan sát:** cơ chế weaving/proxy có áp dụng với mọi đường gọi mong muốn không?
6. **Độ tin cậy ngữ cảnh:** tenant, quyền và version lấy ở đâu, có ổn định trong suốt lời gọi không?

Một *around advice* cần bảo toàn return type, ngoại lệ và ngữ nghĩa đồng bộ/bất đồng bộ. Nó không được gọi phương thức gốc nhiều lần chỉ vì kỹ thuật kiểm tra cache, trừ khi hợp đồng chính sách chủ động quy định retry. Không thực hiện truy cập cache bằng khóa tạo từ toString() của toàn bộ arguments hoặc từ chuỗi tham số chưa được kiểm duyệt.

Đối với **phương thức trả Future/CompletionStage**, cache chính đối tượng Future không tự tương đương với cache **kết quả đã hoàn tất**. Future có trạng thái, cancellation, timeout và ngữ nghĩa chia sẻ; người gọi huỷ handle chung có thể ảnh hưởng người gọi khác. Muốn cache async cần thiết kế cách dùng chung công việc đang chạy, cách phân phối kết quả, lỗi, huỷ và TTL sau hoàn tất. Không gọi get()/join() bên trong advice chỉ để biến kết quả async thành giá trị cache đồng bộ.

Với các hàm trả Stream, Iterator, InputStream hoặc thực thể mutable, cần cân nhắc việc dữ liệu có bị tiêu thụ một lần hoặc bị người gọi sửa sau khi cache hay không. Có thể phải lưu một dạng snapshot bất biến hoặc copy khi đọc/ghi cache; không mặc định rằng một object có thể chia sẻ tự do.

## 8. Hiệu lực, TTL, invalidation và phiên bản hóa

Khóa mô tả sự tương đương giữa hai lời gọi, còn **vòng đời cache** quyết định kết quả có còn hợp lệ tại thời điểm lấy ra không. Hai vấn đề bổ sung nhau nhưng không thay thế nhau.

### 8.1. Time-to-live (TTL)

TTL đặt thời gian tối đa entry có thể được phục vụ hoặc có hiệu lực theo chính sách; nó là cách giới hạn độ cũ, không đảm bảo dữ liệu mới ngay lập tức khi nguồn thay đổi. Với dữ liệu tài chính, quyền truy cập hoặc tồn kho biến động nhanh, TTL dài có thể không chấp nhận được.

Cần nêu rõ TTL tính từ khi tải xong, từ lúc ghi, hay được gia hạn khi đọc. Cache hit cao với dữ liệu sai không phải thành công.

### 8.2. Invalidation theo thay đổi dữ liệu

Khi nguồn dữ liệu đổi, có thể xóa những khóa phụ thuộc, xóa theo nhóm hoặc tăng revision/version rồi dùng khóa mới. Ví dụ đưa catalogVersion vào khóa cho phép bản giá ở phiên bản 2 không dùng nhầm entry của phiên bản 1. Tuy nhiên entry cũ vẫn chiếm bộ nhớ: cần chính sách eviction, giới hạn dung lượng hoặc dọn theo phiên bản.

Nếu có cache cục bộ ở nhiều tiến trình, invalidation phải được lan truyền phù hợp. Một process không nhận sự kiện invalidation vẫn có thể tiếp tục trả entry cũ; hệ thống cần xác định mức nhất quán có thể chấp nhận.

### 8.3. Version của thuật toán và format khóa

Khi thay công thức tính nhưng tên phương thức và tham số giữ nguyên, cache cũ có thể không hợp lệ dù dữ liệu chưa đổi. Cần đổi **schemaVersion/algorithmVersion** hoặc namespace để tách kết quả của thuật toán mới. Đây là lý do ví dụ đưa schemaVersion=1 vào CacheKey.

**Không nên** dùng version cố định mãi mà không có quy trình tăng phiên bản khi ý nghĩa khóa thay đổi; cũng không nên dùng thời gian hiện tại làm version ở mỗi lời gọi vì vô hiệu hóa cache.

## 9. Bảo mật và phân vùng cache

Khóa cache cũng là ranh giới ngăn dữ liệu của những người gọi không có quyền xem chéo nhau. Nếu kết quả đã được lọc theo quyền, khóa dùng chung cần phản ánh **phạm vi quyền của kết quả**, không chỉ tham số hiển thị.

Các lựa chọn phổ biến:

- **Dữ liệu công khai, giống nhau với mọi người:** cache chia sẻ theo tham số và version có thể phù hợp.
- **Dữ liệu theo tenant:** khóa hoặc namespace phải phân vùng tenant; việc truy cập cache vẫn phải qua kiểm tra quyền.
- **Dữ liệu theo nhóm quyền:** dùng scope/role/entitlement version ổn định nếu mọi người trong nhóm được phép chia sẻ cùng kết quả.
- **Dữ liệu cá nhân hóa:** cân nhắc định danh tài khoản hoặc user trong khóa, hoặc bỏ cache chia sẻ nếu rủi ro quá lớn.

Điều quan trọng: **khóa cache không phải cơ chế phân quyền**. Kiểm tra authorization phải được thực hiện theo chính sách tại ranh giới cần thiết; cache hit không được trở thành đường vòng bỏ qua kiểm tra. Không đưa token đăng nhập, mật khẩu, cookie phiên, khóa bí mật hoặc thông tin nhạy cảm dạng thô vào khóa, đặc biệt nếu key được gửi tới cache phân tán và ghi log. Khi cần fingerprint của quyền, nó phải được thiết kế để ổn định, không làm lộ bí mật, và thay đổi khi quyền đổi.

Nếu dữ liệu có khả năng thay đổi do quyền truy cập bị thu hồi, việc giữ entry sau khi thu hồi không được làm lộ thông tin qua cache hit. Cần invalidation/TTL và kiểm tra quyền độc lập theo yêu cầu bảo mật.

## 10. Vấn đề đồng thời và tải đột biến

Khi nhiều luồng cùng gọi một key đang miss, nếu mỗi luồng đều chạy phép tính, hệ thống gặp **cache stampede**. Trong AOP, advice áp dụng rộng có thể khuếch đại vấn đề khi nhiều join point đồng thời cache một thao tác.

Các kỹ thuật tùy yêu cầu:

- **Single-flight theo khóa:** nhiều người đợi chung một lần tải; cần timeout, xử lý cancellation và không giữ lock quá lâu.
- **TTL có jitter:** giảm khả năng hàng loạt entry hết hạn cùng lúc.
- **Giới hạn bộ nhớ/eviction:** tránh tăng số key vô hạn do đầu vào có cardinality cao.
- **Stale-while-revalidate:** trả dữ liệu cũ trong giới hạn được chấp nhận và cập nhật nền, **chỉ khi domain cho phép dữ liệu cũ**.
- **Negative caching:** lưu kết quả không tìm thấy trong thời gian ngắn khi phù hợp, tránh biến lỗi hạ tầng tạm thời thành kết quả “không có dữ liệu” kéo dài.

Với cache phân tán, tính nguyên tử trong một ConcurrentHashMap của một JVM **không** đồng nghĩa với single-flight trên nhiều máy. Phải chọn giải pháp đồng bộ/tải lại ở quy mô triển khai thực tế. Một distributed lock cũng không tự bảo đảm tính đúng của khóa; cùng khóa vẫn phải biểu diễn đúng các điều kiện đầu vào.

## 11. Cách đo và xác minh chính sách cache bằng AOP

Aspect quan sát có thể đo cache hit, miss, thời gian tra cứu, thời gian tính toán nguồn, tỉ lệ lỗi tải cache và số lần eviction. Tên metric cần phân biệt rõ:

~~~text
cache.lookup{operation="quote",result="hit"}
cache.lookup{operation="quote",result="miss"}
cache.load.duration{operation="quote"}
cache.load.failure{operation="quote"}
~~~

Đây là nhãn metric minh họa. Không đưa SKU, tenant ID, request ID hoặc toàn bộ cache key vào label của hệ thống metric nếu chúng có cardinality lớn; dùng chúng trong log chẩn đoán có kiểm soát quyền truy cập khi thực sự cần. Cache hit rate cao có thể đi kèm kết quả sai nếu khóa thiếu ngữ cảnh, vì vậy cần kiểm thử tính đúng song song với kiểm thử hiệu năng.

### Các ca kiểm thử thiết yếu

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Cùng tenant, scope, version và input đã chuẩn hóa | Dùng chung entry; giá trị đúng |
| Khác tenant | Không chia sẻ kết quả nếu tenant ảnh hưởng dữ liệu |
| Khác nhóm quyền/giá | Tạo key khác khi kết quả phụ thuộc nhóm |
| Khác currency/locale/timezone có nghĩa | Tạo key khác hoặc dữ liệu đúng theo contract |
| Khác version dữ liệu/thuật toán | Không dùng entry của version cũ |
| Hai input nhìn giống nhưng domain phân biệt | Không bị gộp nhầm bởi bước chuẩn hóa |
| Input bằng null, rỗng, chứa ký tự phân tách | Không va chạm khóa hoặc bị từ chối rõ ràng |
| Exception khi compute | Truyền lỗi đúng; chỉ cache lỗi nếu có chính sách |
| Nhiều luồng cùng key | Không race dữ liệu; số phép tính theo chính sách |
| Quyền bị thu hồi | Cache hit không vượt qua kiểm tra quyền |
| Nguồn dữ liệu cập nhật | Invalidation hoặc version hóa hoạt động |
| Kết quả có mutable state | Người gọi này không sửa kết quả người khác |

Một bộ kiểm thử tốt nên có ít nhất một trường hợp chứng minh **thiếu thành phần khóa làm sai dữ liệu** rồi xác nhận đã sửa. Ví dụ bỏ tenant khỏi CacheKey sẽ khiến giá của BETA có thể nhận 101 từ ACME thay vì 601, nếu các trường còn lại giống nhau và ACME gọi trước.

## 12. Checklist thiết kế một cache aspect đúng

Trước khi bật cache cho một pointcut:

1. Xác định rõ operation được cache, đầu vào, output và khả năng có tác dụng phụ.
2. Liệt kê tất cả phụ thuộc ảnh hưởng kết quả: tham số, tenant, quyền, locale, version, trạng thái cấu hình và dữ liệu nguồn.
3. Phân định những phụ thuộc nào cần thành phần khóa, những phụ thuộc nào được xử lý bằng invalidation hoặc TTL.
4. Chuẩn hóa dữ liệu theo **ngữ nghĩa domain**, đảm bảo tính toán dùng cùng dạng chuẩn.
5. Thiết kế key bất biến, có kiểu hoặc canonical serialization có schema version; tránh nối chuỗi mơ hồ.
6. Xác định cách cache null, exception, timeout, negative result, Future và kết quả mutable.
7. Đảm bảo cache hit không bỏ qua authorization và không làm mất tác dụng phụ bắt buộc.
8. Thiết lập eviction, giới hạn dung lượng, TTL và chính sách invalidation theo yêu cầu nhất quán.
9. Kiểm thử các trường hợp phân vùng tenant/quyền, đổi version, concurrency và đầu vào tương đương/khác biệt.
10. Đo hit/miss và latency với nhãn ít biến thể, đồng thời theo dõi tính đúng bằng kiểm thử nghiệp vụ.

**Nguyên tắc kết luận:** AOP là vị trí thuận lợi để triển khai **cơ chế cache xuyên suốt**, nhưng khóa cache phải được xác định theo **hợp đồng dữ liệu và ngữ cảnh nghiệp vụ** của phép tính. Hai lời gọi chỉ nên dùng chung entry khi người gọi được phép nhìn cùng kết quả và dữ liệu đó vẫn còn hiệu lực. Khóa đúng, chính sách hết hạn đúng và ranh giới phân quyền đúng là ba điều kiện phải đi cùng nhau.
