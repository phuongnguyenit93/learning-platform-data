# Làm nóng JIT mà không tạo giao dịch hoặc dữ liệu nghiệp vụ thật

Khi khởi động ứng dụng Java, nhiều method ban đầu có thể chạy bằng interpreter. JVM thu thập thông tin về tần suất gọi, kiểu dữ liệu và hành vi của các nhánh. Những method đủ nóng có thể được JIT compiler biên dịch thành mã máy để chạy nhanh hơn. Quá trình chủ động gọi các đường code quan trọng trước khi phục vụ request thật thường được gọi là warmup.

Với CRaC, ứng dụng có thể thực hiện warmup trước khi tạo checkpoint để trạng thái JVM đã được chuẩn bị sẵn. Tuy nhiên, warmup cần tách khỏi nghiệp vụ thật. Mục tiêu là làm nóng những phép tính và đường xử lý cần thiết bằng dữ liệu tổng hợp, adapter trong bộ nhớ hoặc collaborator giả lập, không tạo đơn hàng, không ghi dữ liệu khách hàng, không trừ tồn kho và không mở transaction database thật.

## 1. JIT warmup thực hiện điều gì?

JVM không nhất thiết biên dịch tất cả method ngay khi ứng dụng khởi động. Với HotSpot và các JVM có tiered compilation, một method thường được thực thi trước, sau đó runtime thu thập profile và quyết định có biên dịch hay không.

Quá trình khái quát:

~~~text
Ứng dụng khởi động
       |
       v
Class loading và initialization
       |
       v
Method chạy bằng interpreter
       |
       v
JVM thu thập invocation / back-edge counters
và profile về kiểu dữ liệu, nhánh, call site
       |
       v
Method trở nên đủ nóng
       |
       v
JIT compiler tạo mã máy
       |
       v
Các lần gọi sau có thể chạy bằng mã đã biên dịch
~~~

JIT có thể tối ưu nhiều đặc điểm của code:

- Inline method nhỏ hoặc được gọi thường xuyên.
- Tối ưu nhánh dựa trên profile đã thu thập.
- Tối ưu truy cập object và kiểm tra kiểu.
- Loại bỏ một số phép tính hoặc nhánh không cần thiết.
- Biên dịch vòng lặp hoặc phần code nóng trong vòng lặp.

JVM có thể dùng nhiều mức biên dịch. Vì vậy, một method đã được biên dịch ở mức ban đầu vẫn có thể được biên dịch lại với tối ưu hóa cao hơn khi runtime có thêm profile. Một số giả định tối ưu cũng có thể bị vô hiệu hóa và khiến method deoptimize rồi quay lại interpreter hoặc được biên dịch lại.

Warmup không đồng nghĩa với việc gọi mỗi method một lần. Một lần gọi thường chỉ đủ để thực thi code và có thể nạp class; nó không bảo đảm method đã đạt ngưỡng biên dịch JIT.

## 2. Phân biệt class loading, initialization và JIT compilation

Ba hoạt động này có liên quan nhưng không giống nhau:

| Hoạt động | Ý nghĩa | Ví dụ |
|---|---|---|
| Class loading | JVM tìm và nạp định nghĩa class | Nạp class PricingService từ classpath |
| Class initialization | Chạy static initializer và khởi tạo static field | Tạo cache hoặc đọc system property trong static block |
| JIT compilation | Biên dịch method nóng thành mã máy | Biên dịch PricingService.quote sau nhiều lần gọi |

Chỉ gọi Class.forName() có thể làm class được nạp và khởi tạo, nhưng không làm nóng mọi method của class. Ngược lại, gọi một method nhiều lần có thể kích hoạt các bước cần thiết và cung cấp profile cho JIT.

Class initialization cũng có thể tạo side effect. Nếu static initializer mở connection, đăng ký listener hoặc đọc secret, việc warmup nạp class có thể kích hoạt các hành động đó. Vì vậy, các thành phần được làm nóng cần có khởi tạo an toàn và có thể kiểm soát.

## 3. Xác định phần code cần làm nóng

Không nên cố làm nóng mọi class và method trong ứng dụng. Hãy bắt đầu từ các đường code có ảnh hưởng rõ ràng tới độ trễ sau khi nhận traffic:

- Quy tắc nghiệp vụ tính toán nhiều hoặc được gọi thường xuyên.
- Chuyển đổi và xác thực dữ liệu request.
- Mapping, serialization và deserialization.
- Các bộ lọc, parser hoặc thuật toán được dùng trên đường request chính.
- Các nhánh xử lý thường gặp của một use case.

Có thể dùng profile từ môi trường kiểm thử hoặc quan sát production để nhận diện đường code nóng. Khi không có profile, hãy chọn một số use case đại diện và các kiểu đầu vào phổ biến.

Warmup nên đại diện cho hình dạng dữ liệu và kiểu thực thi thực tế:

- Có nhiều giá trị đầu vào khác nhau thay vì lặp một hằng số duy nhất.
- Đi qua các nhánh nghiệp vụ phổ biến.
- Dùng các kiểu triển khai thực tế tại call site nếu cần làm nóng code đa hình.
- Tránh chỉ gọi một đường code hiếm gặp rồi kết luận toàn bộ use case đã nóng.

JIT tối ưu dựa trên profile. Nếu warmup chỉ dùng một kiểu implementation nhưng traffic thật dùng nhiều kiểu khác nhau, giả định tối ưu có thể không còn phù hợp và JVM có thể deoptimize hoặc biên dịch lại.

## 4. Tách logic tính toán khỏi transaction và side effect

Một cách hiệu quả để warmup mà không tạo giao dịch thật là tách logic thuần khỏi lớp điều phối persistence và side effect.

Ví dụ, xử lý đặt hàng có thể gồm:

~~~text
HTTP request
    |
    v
Application service (@Transactional)
    |
    +----> Đọc dữ liệu từ repository
    |
    +----> Gọi payment gateway
    |
    +----> Ghi đơn hàng và tồn kho
    |
    v
Commit transaction

Đường warmup:
Warmup runner
    |
    v
Domain / computation service
    |
    +----> Synthetic input
    |
    +----> In-memory catalog hoặc fake collaborator
    |
    v
Kết quả tổng hợp, không có ghi nghiệp vụ
~~~

Warmup gọi trực tiếp phần tính toán cần tối ưu, không gọi application service mở transaction, không gọi repository thật và không gọi payment hoặc message gateway thật.

Nếu một method có annotation **@Transactional**, việc gọi method đó có thể kích hoạt transaction manager ngay cả khi code bên trong không ghi dữ liệu. **@Transactional(readOnly = true)** cũng vẫn có thể mở transaction và session; thuộc tính readOnly không phải một bảo đảm chung rằng sẽ không có side effect. Vì vậy, không nên dùng rollback transaction như một cách mặc định để làm nóng JIT.

Rollback cũng không hoàn tác được mọi side effect. Sequence có thể đã tăng, message có thể đã gửi, email có thể đã phát, audit log có thể đã ghi, hoặc một dịch vụ ngoài đã xử lý request. Cách an toàn là không gọi các adapter gây side effect trong đường warmup.

## 5. Ví dụ: làm nóng logic báo giá bằng dữ liệu tổng hợp

Ví dụ sau sử dụng một PricingService chứa logic tính giá. Catalog là một interface; warmup dùng catalog trong bộ nhớ với các mã sản phẩm giả lập. Đường code này không dùng JDBC, transaction manager, message broker hoặc payment gateway.

~~~java
import java.util.List;
import java.util.Map;

public final class JitWarmupExample {
    record Product(String sku, int unitPriceCents, int taxBasisPoints) {}

    record QuoteRequest(String sku, int quantity, String region) {}

    record Quote(String sku, int quantity, long subtotalCents,
                 long taxCents, long totalCents) {}

    interface Catalog {
        Product find(String sku);
    }

    static final class PricingService {
        private final Catalog catalog;

        PricingService(Catalog catalog) {
            this.catalog = catalog;
        }

        Quote quote(QuoteRequest request) {
            if (request.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }

            Product product = catalog.find(request.sku());
            if (product == null) {
                throw new IllegalArgumentException("Unknown SKU");
            }

            long subtotal = (long) product.unitPriceCents()
                    * request.quantity();
            long tax = (subtotal * product.taxBasisPoints() + 5_000L)
                    / 10_000L;
            long total = subtotal + tax;

            return new Quote(
                    product.sku(),
                    request.quantity(),
                    subtotal,
                    tax,
                    total);
        }
    }

    static final class WarmupRunner {
        private static volatile long resultSink;

        long warm(PricingService pricingService) {
            List<QuoteRequest> samples = List.of(
                    new QuoteRequest("SYNTH-A", 1, "VN"),
                    new QuoteRequest("SYNTH-B", 3, "VN"),
                    new QuoteRequest("SYNTH-A", 5, "SG"),
                    new QuoteRequest("SYNTH-C", 2, "SG"));

            long checksum = 0;
            int rounds = 20_000; // Chỉ là giá trị minh họa.

            for (int i = 0; i < rounds; i++) {
                Quote quote = pricingService.quote(
                        samples.get(i % samples.size()));
                checksum = checksum * 31 + quote.totalCents();
            }

            resultSink = checksum;
            return resultSink;
        }
    }

    public static void main(String[] args) {
        Map<String, Product> syntheticProducts = Map.of(
                "SYNTH-A", new Product("SYNTH-A", 12_500, 800),
                "SYNTH-B", new Product("SYNTH-B", 7_900, 500),
                "SYNTH-C", new Product("SYNTH-C", 21_000, 1_000));

        Catalog inMemoryCatalog = syntheticProducts::get;
        PricingService pricingService =
                new PricingService(inMemoryCatalog);

        long checksum = new WarmupRunner().warm(pricingService);
        System.out.println("Warmup completed: " + checksum);
    }
}
~~~

Ví dụ minh họa một số nguyên tắc:

- Warmup gọi chính method quote chứa logic cần làm nóng.
- Các request và SKU đều là dữ liệu tổng hợp, không đại diện cho khách hàng hoặc đơn hàng thật.
- Catalog chỉ đọc từ Map trong bộ nhớ.
- Không có repository ghi dữ liệu, transaction database, payment hoặc message.
- Kết quả được đưa vào checksum và volatile field để kết quả tính toán có thể quan sát được, tránh biến warmup thành một vòng lặp hoàn toàn không có tác dụng.

Số vòng lặp 20.000 chỉ là con số minh họa, không phải ngưỡng JIT được bảo đảm. Ngưỡng biên dịch phụ thuộc JVM, tiered compilation, profile, kích thước method và các cờ runtime. Cần chọn số vòng theo ngân sách startup và đo trên đúng runtime triển khai.

Trong ứng dụng thực tế, PricingService có thể là domain service được dùng bởi application service. Application service thật vẫn mở transaction và gọi repository khi xử lý request. Warmup chỉ tạo PricingService với collaborator trong bộ nhớ và gọi phần tính toán thuần.

## 6. Làm nóng nhiều nhánh nhưng giữ dữ liệu giả lập

Nếu một method có nhiều nhánh, warmup cần đi qua những nhánh quan trọng. Ví dụ:

- Sản phẩm thuộc nhiều nhóm thuế.
- Số lượng ở các khoảng khác nhau.
- Các loại tiền tệ hoặc khu vực hợp lệ.
- Trường hợp giảm giá và không giảm giá.
- Đầu vào hợp lệ và lỗi thường gặp nếu nhánh xử lý lỗi quan trọng.

Không cần tạo một bộ dữ liệu lớn hoặc giống hệt production. Chỉ cần các mẫu tổng hợp đủ đa dạng để code chạy qua những nhánh cần thiết.

Tránh lặp cùng một object bất biến với mọi giá trị giống hệt nhau nếu traffic thật có nhiều kiểu đầu vào. JIT có thể tối ưu dựa trên profile quá hẹp. Dùng nhiều mẫu tổng hợp đại diện cho các nhánh quan trọng.

Nếu call site sử dụng nhiều implementation, ví dụ nhiều loại TaxPolicy hoặc Serializer, có thể đưa các implementation đại diện vào warmup. Điều này giúp profile phản ánh gần hơn kiểu gọi thực tế. Chỉ dùng những implementation không tạo side effect và có vòng đời an toàn.

## 7. Những gì warmup không nên gọi

Để không tạo giao dịch hoặc dữ liệu nghiệp vụ thật, tránh gọi trực tiếp:

- Application service có **@Transactional** hoặc transaction boundary khác.
- Repository thật có thể INSERT, UPDATE, DELETE hoặc tạo audit record.
- Payment gateway, email service, SMS provider hoặc dịch vụ gửi thông báo.
- Message publisher hoặc consumer xử lý message thật.
- API tạo đơn hàng, đặt chỗ, trừ tồn kho, cấp tài khoản hoặc thay đổi trạng thái khách hàng.
- Scheduler thật có thể phát sinh công việc định kỳ.
- Các API bên ngoài có side effect dù request được gọi với mục đích warmup.

Không nên nghĩ rằng dùng một request có gắn header warmup=true là đủ để tránh side effect. Mỗi adapter phải có chính sách rõ ràng để không gửi dữ liệu ra ngoài hoặc ghi dữ liệu nghiệp vụ. Cách tốt hơn là dùng dependency riêng trong warmup, được cấu hình bằng in-memory implementation hoặc no-op implementation.

Nếu cần khởi tạo class hoặc parser của một thư viện, hãy xác định static initializer và constructor có mở tài nguyên, đăng ký listener, gửi telemetry hoặc đọc secret hay không. Class loading có thể kích hoạt code khởi tạo; warmup cần tính đến điều này.

## 8. Vì sao rollback không phải là chiến lược warmup an toàn?

Một cách làm dễ nghĩ tới là chạy use case thật trong transaction rồi rollback sau khi warmup. Cách này không bảo đảm ứng dụng không tạo dữ liệu hoặc side effect thật:

- Database sequence/identity có thể vẫn tăng dù transaction rollback.
- Trigger hoặc extension có thể gọi hệ thống bên ngoài.
- Message hoặc email có thể đã được gửi trước rollback.
- Một số hệ thống lưu trữ hoặc API không hỗ trợ transaction rollback.
- Cache, metric, audit log hoặc bộ đếm bên ngoài có thể đã thay đổi.
- Transaction thật tiêu tốn connection, lock và tài nguyên database.

Ngay cả khi database rollback hoàn toàn, việc mở transaction vẫn vi phạm mục tiêu warmup không tạo transaction thật. Vì vậy, warmup nên chạy trên phần logic không cần transaction hoặc dùng adapter giả lập.

## 9. Kết hợp JIT warmup với CRaC checkpoint

Một quy trình startup có thể gồm:

~~~text
Khởi tạo JVM và framework
       |
       v
Nạp class và tạo bean cần thiết
       |
       v
Khởi tạo dependency an toàn
       |
       v
Chạy JIT warmup bằng dữ liệu tổng hợp
       |
       v
Đợi warmup kết thúc và đóng executor tạm
       |
       v
Đưa ứng dụng về trạng thái quiescent
       |
       v
Tạo checkpoint CRaC
       |
       v
Restore khi triển khai
       |
       v
Xác minh dependency và readiness
       |
       v
Nhận traffic thật
~~~

Warmup cần hoàn tất trước khi tạo checkpoint. Không để executor warmup, virtual thread hoặc task nền tiếp tục chạy mà không có chính sách vòng đời rõ ràng. Nếu warmup mở tài nguyên tạm, hãy đóng chúng trước checkpoint hoặc để Resource sở hữu và quản lý đúng theo hướng dẫn của thư viện.

JVM có thể giữ lại trạng thái JIT đã biên dịch trong checkpoint image, nhưng không nên giả định mọi method đã được biên dịch sẽ luôn giữ nguyên mã máy hoặc không bao giờ phải biên dịch lại. Runtime có thể deoptimize hoặc biên dịch lại khi profile và giả định tối ưu thay đổi. Hành vi thực tế phụ thuộc JDK, vendor, kiến trúc CPU, flags và CRaC implementation.

Vì vậy, warmup trước checkpoint là cách chuẩn bị runtime, không phải cam kết rằng mọi request sau restore đều chạy ở trạng thái tối ưu tối đa ngay từ đầu.

## 10. Warmup không thay thế việc khôi phục dependency

Warmup bằng fake adapter chỉ làm nóng code đã được gọi. Nó không làm nóng database server, connection pool thật, TLS handshake, DNS cache, broker connection hoặc remote service.

Ví dụ, gọi PricingService với in-memory Catalog có thể làm nóng logic tính giá, nhưng không biên dịch hoặc khởi tạo toàn bộ đường JDBC của repository thật. Nếu mục tiêu cần kiểm tra kết nối database, đó là một bước preflight riêng và có thể mở connection hoặc transaction tùy driver/database.

Hãy tách hai mục tiêu:

- **JIT warmup an toàn:** gọi logic cần tối ưu bằng dữ liệu tổng hợp và adapter không side effect.
- **Dependency readiness:** kiểm tra kết nối tới dịch vụ bên ngoài theo chính sách được phép. Bước này phải được thiết kế riêng, có giới hạn quyền và không được nhầm là warmup không giao dịch.

Sau restore, dependency cần được xác minh theo vòng đời của chúng. Một JIT method đã nóng không chứng minh database connection còn hợp lệ hoặc credential vẫn còn hiệu lực.

## 11. Đo lường warmup và quan sát JIT

Warmup nên được đo bằng thời gian, mức sử dụng CPU, số lần gọi và độ trễ của đường code sau khi warmup. Không nên chọn số vòng lặp chỉ vì một con số cố định có vẻ đủ lớn.

Với HotSpot, có thể dùng tùy chọn chẩn đoán **-XX:+PrintCompilation** trong môi trường thử nghiệm để quan sát các sự kiện biên dịch. Output và tùy chọn chẩn đoán có thể khác giữa các JVM và bản phát hành. Không nên bật log chi tiết này trong production nếu chưa đánh giá tác động.

JFR và các công cụ profiling của JDK có thể giúp quan sát hoạt động compilation và CPU. Hãy dùng cấu hình phù hợp với JDK mục tiêu để xác định method nào thực sự được biên dịch và thời điểm biên dịch.

Khi đo, cần phân biệt:

- Thời gian class loading/initialization.
- Thời gian warmup và compilation.
- Thời gian GC phát sinh do dữ liệu tổng hợp.
- Độ trễ của method sau warmup.
- Độ trễ sau restore và số lần deoptimization/recompilation nếu có.

Một bài benchmark cần kiểm soát môi trường và dữ liệu. Nếu cần so sánh hiệu năng thuật toán một cách nghiêm túc, dùng JMH trong môi trường benchmark riêng; không lấy một vòng lặp startup đơn giản làm kết quả benchmark chính xác.

## 12. Các lỗi thường gặp

**Gọi application service thật để làm nóng.**

Method có thể mở transaction, ghi dữ liệu hoặc gọi hệ thống bên ngoài. Tách phần logic thuần và gọi trực tiếp phần đó bằng collaborator giả lập.

**Dùng transaction rồi rollback.**

Rollback không hoàn tác mọi side effect và vẫn tạo transaction thật. Không dùng cách này khi mục tiêu là warmup không giao dịch.

**Dùng dữ liệu production.**

Không cần dữ liệu khách hàng hoặc đơn hàng thật để làm nóng JIT. Tạo bộ dữ liệu tổng hợp có hình dạng đại diện và không chứa thông tin cá nhân.

**Chỉ gọi method một lần.**

Một lần gọi không bảo đảm method đạt ngưỡng JIT. Chọn số lần gọi dựa trên đo lường và ngân sách startup.

**Lặp một đầu vào cố định.**

JIT có thể tối ưu dựa trên profile quá hẹp. Dùng nhiều mẫu tổng hợp đại diện cho các nhánh quan trọng.

**Warmup quá nhiều.**

Warmup kéo dài làm chậm startup, tăng CPU, allocation và GC. Chỉ làm nóng những đường code có giá trị rõ ràng.

**Giả định warmup làm nóng mọi thư viện và dependency.**

Fake adapter không gọi code của driver hoặc remote client thật. Warmup logic và kiểm tra dependency là hai bước khác nhau.

**Để task warmup chạy qua checkpoint.**

Task còn chạy có thể giữ object tạm, thread hoặc tài nguyên. Chờ hoàn tất và đóng executor trước khi checkpoint.

**Cho rằng mã JIT sẽ không bao giờ bị biên dịch lại sau restore.**

JVM có thể deoptimize hoặc compile lại. Cần đo trên đúng JDK, vendor, kiến trúc và cấu hình CRaC.

## 13. Quy trình triển khai an toàn

Một quy trình thực tế:

1. Chọn các method và use case có ảnh hưởng tới latency.
2. Tách logic tính toán khỏi transaction, persistence và side effect.
3. Tạo input tổng hợp với nhiều giá trị và nhánh đại diện.
4. Dùng in-memory hoặc no-op adapter cho mọi dependency không được phép tạo side effect.
5. Gọi trực tiếp phần code cần làm nóng, không gọi facade mở transaction.
6. Đo thời gian warmup và độ trễ sau warmup để điều chỉnh số vòng.
7. Đảm bảo mọi task warmup hoàn tất và executor tạm đã đóng.
8. Đưa ứng dụng về trạng thái quiescent rồi tạo checkpoint.
9. Sau restore, kiểm tra dependency, cấu hình và readiness trước khi nhận traffic.
10. Kiểm thử nhiều lần checkpoint/restore để xác nhận không tạo dữ liệu nghiệp vụ, transaction, message hoặc tác vụ nền ngoài dự kiến.

## 14. Kết luận

JIT warmup giúp JVM thu thập profile và biên dịch những method nóng trước khi ứng dụng phục vụ traffic thật. Trong ứng dụng CRaC, warmup có thể được thực hiện trước checkpoint để chuẩn bị các đường code quan trọng.

Để warmup không tạo giao dịch hoặc dữ liệu nghiệp vụ thật, hãy tách logic tính toán khỏi transaction boundary và adapter gây side effect. Dùng dữ liệu tổng hợp, in-memory collaborator hoặc no-op adapter; không gọi application service thật, không dựa vào rollback và không gửi request tới hệ thống nghiệp vụ. Warmup cần kết thúc trước checkpoint, còn khả năng giữ mã JIT sau restore phải được xác nhận trên đúng JDK và CRaC runtime triển khai.
