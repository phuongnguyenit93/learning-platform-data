# Enrichment processor trong Spring Batch

Trong nhiều batch job, dữ liệu đọc từ file hoặc database chưa có đủ thông tin để ghi vào hệ thống đích. Một customer record có thể chỉ chứa customer code, trong khi dữ liệu đích cần tên chuẩn hóa, nhóm khách hàng, vùng kinh doanh và trạng thái phân loại. Một order có thể chứa product ID nhưng cần thêm product category, tax rate hoặc thông tin đơn vị giao hàng trước khi tính toán.

Enrichment processor là một ItemProcessor bổ sung dữ liệu cần thiết cho item trước khi chuyển nó sang writer. Processor thường tra cứu reference data, gọi một service đọc dữ liệu hoặc kết hợp dữ liệu đã được nạp sẵn. Kết quả là một item giàu thông tin hơn, sẵn sàng cho validation nghiệp vụ tiếp theo hoặc mapping sang mô hình ghi.

Enrichment cần được thiết kế cùng hiệu năng, tính nhất quán và khả năng restart. Nếu mỗi item đều gọi một API hoặc query riêng, job có thể tạo N+1 request và chạy rất chậm. Nếu reference data thay đổi giữa các lần chạy, cùng một input có thể được enrich thành kết quả khác. Nếu processor tạo side effect hoặc tự ghi dữ liệu, retry và rollback của chunk sẽ khó kiểm soát.

## 1. Enrichment processor là gì?

Trong chunk-oriented processing, ItemProcessor nhận một item đã đọc, thực hiện logic xử lý và trả về item đầu ra. Enrichment là một dạng xử lý mà trọng tâm là bổ sung thông tin từ nguồn khác.

~~~text
Input source
    |
    v
ItemReader<CustomerInput>
    |
    v
EnrichmentProcessor
    |
    +----> Lookup customer profile
    |
    +----> Lookup region reference
    |
    +----> Lookup pricing/rules
    |
    v
EnrichedCustomer
    |
    v
ItemWriter<EnrichedCustomer>
~~~

Ví dụ input chỉ có:

~~~json
{
  "customerCode": "C-100",
  "regionCode": "SOUTH"
}
~~~

Sau enrichment, item có thể chứa thêm tên customer, tier, địa chỉ chuẩn hóa và tên vùng:

~~~json
{
  "customerCode": "C-100",
  "customerName": "Example Trading",
  "customerTier": "GOLD",
  "regionCode": "SOUTH",
  "regionName": "Southern Region"
}
~~~

Processor không nhất thiết phải gọi nhiều nguồn. Enrichment có thể chỉ là một lookup từ bảng reference, một phép tra cứu cache hoặc kết hợp dữ liệu từ một service. Điều quan trọng là kết quả đầu ra có thêm thông tin cần cho bước xử lý sau.

## 2. Enrichment khác với validation và transformation

Ba loại logic này thường cùng xuất hiện trong processor nhưng có mục tiêu khác nhau:

| Loại xử lý | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Validation | Kiểm tra item có đáp ứng quy tắc hay không | customerCode bắt buộc, amount phải dương |
| Enrichment | Bổ sung dữ liệu từ nguồn khác | Tra cứu customer tier theo customerCode |
| Transformation | Chuyển dữ liệu sang dạng khác | Đổi CustomerInput thành CustomerEntity |

Một processor có thể thực hiện cả ba, nhưng nên tách logic thành các thành phần dễ hiểu và kiểm thử. Ví dụ, kiểm tra input trước khi gọi service tránh tốn request cho item chắc chắn không hợp lệ. Enrichment sau đó bổ sung dữ liệu. Mapper cuối cùng tạo output model cho writer.

Nếu enrichment chỉ là một bước trong pipeline, có thể dùng CompositeItemProcessor để ghép nhiều processor theo thứ tự. Khi đó output của processor trước là input của processor tiếp theo.

## 3. Tạo processor enrichment cơ bản

Giả sử nguồn cung cấp customer code và region code. Processor tra cứu customer profile và region reference:

~~~java
public class CustomerEnrichmentProcessor
        implements ItemProcessor<CustomerInput, EnrichedCustomer> {

    private final CustomerProfileService customerProfiles;
    private final RegionService regions;

    public CustomerEnrichmentProcessor(
            CustomerProfileService customerProfiles,
            RegionService regions) {
        this.customerProfiles = customerProfiles;
        this.regions = regions;
    }

    @Override
    public EnrichedCustomer process(CustomerInput input) {
        CustomerProfile profile =
            customerProfiles.findByCode(input.customerCode())
                .orElseThrow(() ->
                    new MissingCustomerException(input.customerCode()));

        Region region =
            regions.findByCode(input.regionCode())
                .orElseThrow(() ->
                    new MissingRegionException(input.regionCode()));

        return new EnrichedCustomer(
            input.customerCode(),
            profile.name(),
            profile.tier(),
            input.regionCode(),
            region.name()
        );
    }
}
~~~

Processor chỉ điều phối việc tra cứu và tạo item đầu ra. Service chịu trách nhiệm truy cập database hoặc API, còn writer chịu trách nhiệm ghi kết quả. Cách tách này giúp thay nguồn enrichment mà không phải viết lại toàn bộ step.

## 4. Dùng constructor injection và cấu hình step

Khai báo processor thành bean để Spring quản lý dependency:

~~~java
@Bean
ItemProcessor<CustomerInput, EnrichedCustomer> customerEnrichmentProcessor(
        CustomerProfileService customerProfiles,
        RegionService regions) {

    return new CustomerEnrichmentProcessor(customerProfiles, regions);
}
~~~

Đăng ký trong step:

~~~java
@Bean
Step enrichCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, EnrichedCustomer> customerEnrichmentProcessor,
        ItemWriter<EnrichedCustomer> customerWriter) {

    return new StepBuilder("enrichCustomersStep", jobRepository)
        .<CustomerInput, EnrichedCustomer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerEnrichmentProcessor)
        .writer(customerWriter)
        .build();
}
~~~

Step định nghĩa kiểu item trước và sau processor. Reader trả CustomerInput, processor trả EnrichedCustomer, writer nhận EnrichedCustomer. Tách kiểu input/output giúp compiler phát hiện nhầm lẫn trong pipeline.

## 5. Giữ input và output tách biệt

Một cách thiết kế rõ ràng là dùng immutable DTO hoặc record cho dữ liệu đầu vào và đầu ra:

~~~java
public record CustomerInput(
    String customerCode,
    String regionCode
) {}

public record EnrichedCustomer(
    String customerCode,
    String customerName,
    String customerTier,
    String regionCode,
    String regionName
) {}
~~~

Processor tạo object mới thay vì sửa trực tiếp input. Điều này giúp:

- Giữ lại payload gốc để audit hoặc so sánh.
- Phân biệt field đến từ nguồn với field được enrich.
- Tránh delegate hoặc listener khác nhìn thấy object bị sửa ngoài dự kiến.
- Dễ unit test vì input và output có giá trị bất biến.

Nếu cần giữ toàn bộ source payload, có thể thêm source reference, source file name, source record number hoặc source batch ID vào output model. Không nhất thiết phải sao chép mọi field nếu writer không cần chúng.

## 6. Enrichment từ database

Một trường hợp phổ biến là tra cứu bảng reference hoặc master data:

~~~java
@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public Optional<CustomerProfile> findByCode(String code) {
        return repository.findByCustomerCode(code);
    }
}
~~~

Processor gọi service theo business key. Cần bảo đảm cột tra cứu có index phù hợp; nếu không, hàng triệu lookup có thể làm database chịu tải nặng.

Nếu mỗi item cần nhiều reference, tránh thực hiện một query cho từng field. Có thể cung cấp một service trả về aggregate enrichment cần thiết trong một lần lookup hoặc dùng một query join/projection ở reader nếu logic và nguồn dữ liệu phù hợp.

## 7. Tránh N+1 query trong enrichment

Giả sử một chunk có 1000 item và processor gọi repository một lần cho mỗi item:

~~~text
1000 input items
  |
  +--> SELECT customer_profile WHERE code = ?
  +--> SELECT customer_profile WHERE code = ?
  +--> SELECT customer_profile WHERE code = ?
  +--> ... 1000 lần
~~~

Đây là dạng N+1 lookup. Dù mỗi query nhanh, tổng latency, connection usage và database load có thể rất lớn.

Thay vào đó, thu thập các key cần tra cứu rồi gọi một query theo nhóm:

~~~sql
select customer_code, customer_name, tier
from customer_profile
where customer_code in (:customerCodes)
~~~

Kết quả được chuyển thành Map theo customer code. Processor tra cứu trong map thay vì gọi database từng item.

Vì ItemProcessor làm việc từng item, việc gom key theo chunk cần được thiết kế ở một thành phần khác hoặc bằng cache/bulk preload. Không nên giả định processor tự nhận toàn bộ chunk.

## 8. Các chiến lược bulk enrichment

Có một số cách giảm số lần tra cứu:

| Chiến lược | Cách làm | Phù hợp khi |
| --- | --- | --- |
| Join trong reader query | Lấy dữ liệu chính và reference trong cùng query | Cùng database và query không quá phức tạp |
| Bulk preload | Nạp reference data trước khi step xử lý | Reference set vừa phải, ít thay đổi |
| Batch lookup service | Gửi một nhóm key tới service | Service hỗ trợ API bulk |
| Cache theo key | Tra cứu lần đầu rồi tái sử dụng | Nhiều item dùng chung reference |
| Chunk-aware custom component | Gom key theo nhóm rồi enrich | Cần batching theo chunk với tập dữ liệu lớn |

Chọn chiến lược theo kích thước dữ liệu, khả năng thay đổi reference, latency và yêu cầu nhất quán. Bulk preload toàn bộ bảng có thể không phù hợp nếu bảng có hàng triệu record.

## 9. Bulk preload trước khi step chạy

Nếu reference data có kích thước vừa phải và cần một snapshot nhất quán cho toàn step, có thể nạp dữ liệu trước khi bắt đầu xử lý. Ví dụ dùng StepExecutionListener để khởi tạo lookup map:

~~~java
public class ReferenceDataListener implements StepExecutionListener {

    private final RegionRepository regionRepository;
    private Map<String, Region> regions;

    public ReferenceDataListener(RegionRepository regionRepository) {
        this.regionRepository = regionRepository;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        this.regions = regionRepository.findAll().stream()
            .collect(Collectors.toUnmodifiableMap(
                Region::code,
                Function.identity()
            ));
    }

    public Region findRegion(String code) {
        return regions.get(code);
    }
}
~~~

Processor có thể nhận listener/service này và tra cứu map. Cần lưu ý lifecycle: listener phải được khởi tạo trước khi processor sử dụng, và state phải được giới hạn theo StepExecution nếu job chạy song song.

Không lưu một mutable map theo step vào singleton bean dùng chung cho nhiều execution đồng thời. Có thể dùng @StepScope hoặc một component giữ state theo execution; bảo đảm worker/partition không ghi đè dữ liệu của nhau.

## 10. Bulk lookup theo từng chunk

Nếu reference data quá lớn để preload toàn bộ nhưng service hỗ trợ lookup nhiều key, có thể xây dựng một lớp batch-aware:

~~~text
Chunk input:
  C-1, C-2, C-1, C-3
       |
       v
Collect distinct keys:
  C-1, C-2, C-3
       |
       v
One bulk lookup
       |
       v
Map<customerCode, CustomerProfile>
       |
       v
Enrich each input item
~~~

Vì hợp đồng ItemProcessor là xử lý một item mỗi lần, việc chuẩn bị lookup map theo chunk cần một điểm tích hợp có quyền nhìn thấy chunk, ví dụ custom chunk-oriented component, cache được nạp từ reader/listener hoặc một bước chuẩn bị dữ liệu trước step. Không nên dùng biến static để tích lũy key giữa các lần process vì chunk boundary, rollback và multi-threading có thể làm trạng thái sai.

Một lựa chọn đơn giản nếu service có thể nhận từng key nhưng nhiều item dùng chung key là cache theo key. Với key khác nhau hoàn toàn, bulk API hoặc join thường hiệu quả hơn.

## 11. Cache trong enrichment processor

Cache hữu ích khi nhiều item tra cứu cùng một reference:

~~~java
public class CachedRegionService {

    private final RegionRepository repository;
    private final ConcurrentMap<String, Region> cache =
        new ConcurrentHashMap<>();

    public CachedRegionService(RegionRepository repository) {
        this.repository = repository;
    }

    public Region findRequired(String code) {
        return cache.computeIfAbsent(code, key ->
            repository.findByCode(key)
                .orElseThrow(() -> new MissingRegionException(key))
        );
    }
}
~~~

Cache giảm query lặp cho cùng key. ConcurrentHashMap giúp thao tác map an toàn ở mức cấu trúc khi nhiều thread truy cập, nhưng không giải quyết tự động invalidation, giới hạn memory hoặc consistency của reference data.

Với job dài hạn, cache không giới hạn có thể tăng memory liên tục. Cân nhắc cache có maximum size, TTL hoặc scope chỉ trong một execution. Nếu reference data thay đổi trong lúc job chạy, cache có thể giữ giá trị cũ.

## 12. Cache theo application hay theo step?

Cache application-wide có thể được dùng lại giữa nhiều job, nhưng cần chính sách refresh và đồng bộ. Cache theo step dễ giới hạn vòng đời và gắn với snapshot của một lần chạy.

| Phạm vi cache | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Application-wide | Tái sử dụng giữa nhiều job, giảm lookup | Dữ liệu cũ, memory lâu dài, đồng thời nhiều tenant |
| Step-scoped | Cô lập theo execution, dễ giải phóng | Mỗi step có thể phải nạp lại dữ liệu |
| Chunk-local | Giới hạn memory, phù hợp lookup theo chunk | Cần cơ chế gom key và nạp map theo chunk |

Nếu key phụ thuộc tenant, locale hoặc business date, cache key phải chứa những yếu tố đó. Chỉ cache theo customer code có thể trả nhầm dữ liệu giữa tenant hoặc kỳ hiệu lực khác nhau.

Không chia sẻ cache chứa dữ liệu tenant-sensitive giữa execution nếu không có partition key và chính sách cách ly rõ ràng.

## 13. Reference data thay đổi theo thời gian

Một enrichment result có thể phụ thuộc vào thời điểm nghiệp vụ:

- Tax rate có hiệu lực từ một ngày cụ thể.
- Customer tier thay đổi theo kỳ.
- Product price có version hoặc effective date.
- Region mapping được cập nhật sau khi job bắt đầu.

Nếu job bị restart vào ngày hôm sau và query lấy reference data hiện tại, cùng input có thể tạo output khác với lần chạy đầu. Điều này có thể làm kết quả không nhất quán.

Các cách kiểm soát:

1. Truy vấn reference theo business date/effective date của job.
2. Lưu reference version hoặc snapshot ID trong JobParameters.
3. Nạp reference snapshot vào staging table.
4. Dùng bảng lịch sử có valid-from/valid-to.
5. Lưu giá trị enrichment đã quyết định nếu nghiệp vụ yêu cầu giữ nguyên kết quả giữa restart.

Không dùng LocalDate.now() trong processor cho logic cần ổn định khi restart. Truyền business date rõ ràng từ JobParameters để cùng một JobInstance dùng cùng mốc thời gian.

## 14. Enrichment qua REST hoặc dịch vụ ngoài

Một processor có thể gọi service bên ngoài để bổ sung thông tin:

~~~java
public class RiskEnrichmentProcessor
        implements ItemProcessor<PaymentInput, EnrichedPayment> {

    private final RiskClient riskClient;

    public RiskEnrichmentProcessor(RiskClient riskClient) {
        this.riskClient = riskClient;
    }

    @Override
    public EnrichedPayment process(PaymentInput input) {
        RiskProfile profile = riskClient.getProfile(input.customerId());
        return new EnrichedPayment(input, profile.score(), profile.level());
    }
}
~~~

Khi gọi remote service, đặt timeout rõ ràng và phân loại lỗi:

- 404 hoặc “profile not found” có thể là kết quả nghiệp vụ.
- 429 hoặc 503 có thể là lỗi tạm thời, tùy hợp đồng API.
- Timeout không cho biết chắc remote server chưa xử lý request.
- 401/403 thường là lỗi credential hoặc quyền, cần fail và xử lý cấu hình.
- Response không đúng schema có thể là contract drift.

Enrichment nên ưu tiên thao tác đọc. Nếu remote call tạo side effect, cần đánh giá lại việc đặt nó trong processor vì retry/rollback có thể gọi lặp. Các thao tác ghi hoặc publish thường phù hợp với writer/outbox hơn.

## 15. Retry cho lookup tạm thời

Nếu API hoặc database lookup tạm thời unavailable, có thể cấu hình retry ở step:

~~~java
return new StepBuilder("enrichPaymentsStep", jobRepository)
    .<PaymentInput, EnrichedPayment>chunk(100, transactionManager)
    .reader(paymentReader)
    .processor(riskEnrichmentProcessor)
    .writer(paymentWriter)
    .faultTolerant()
    .retry(TransientEnrichmentException.class)
    .retryLimit(3)
    .build();
~~~

Chỉ wrap exception thành TransientEnrichmentException khi biết lỗi có khả năng tự hết. Không retry mọi RuntimeException, vì lỗi mapping, thiếu reference vĩnh viễn hoặc code bug sẽ không tự sửa.

Retry ở processor có thể khiến processor được gọi lại cho item. Processor vì thế nên không tạo side effect không idempotent. Với remote read, request lặp thường an toàn, nhưng cần chú ý rate limit và chi phí.

Nếu retry hết giới hạn, step có thể fail. Scheduler/operator có thể restart JobInstance sau khi dịch vụ phục hồi; query parameters và reference version cần giữ ổn định để output không đổi ngoài ý muốn.

## 16. Missing reference: default, skip, quarantine hay fail?

Không phải mọi lookup không tìm thấy dữ liệu đều là lỗi hạ tầng. Đó có thể là tình huống nghiệp vụ cần xử lý rõ:

| Tình huống | Hướng xử lý |
| --- | --- |
| Reference tùy chọn, có default được quy định | Dùng default và ghi nhận nguồn default |
| Reference bắt buộc nhưng thiếu ở một vài item | Skip/quarantine nếu được phép |
| Reference thiếu cho toàn bộ một loại dữ liệu | Fail step/job vì có thể là lỗi nguồn hoặc cấu hình |
| Lookup service tạm thời không phản hồi | Retry có giới hạn |
| Reference không còn hiệu lực tại business date | Áp dụng rule lịch sử hoặc từ chối |

Không tự thay giá trị null bằng một default chung chỉ để job hoàn tất. Một customer không tìm thấy có thể không được phép gán vào nhóm mặc định; làm vậy sẽ tạo dữ liệu sai nhưng trông có vẻ hợp lệ.

## 17. Thể hiện missing reference bằng exception riêng

Dùng exception riêng giúp skip policy nhận diện đúng lỗi nghiệp vụ:

~~~java
public class MissingCustomerProfileException
        extends RuntimeException {

    public MissingCustomerProfileException(String customerCode) {
        super("No customer profile for code: " + customerCode);
    }
}
~~~

Processor:

~~~java
CustomerProfile profile = customerProfiles.findByCode(code)
    .orElseThrow(() -> new MissingCustomerProfileException(code));
~~~

Step có thể skip loại lỗi đó nếu business owner cho phép:

~~~java
.faultTolerant()
.skip(MissingCustomerProfileException.class)
.skipLimit(100)
~~~

Đối với record bị skip, dùng SkipListener để lưu business key, source location và lý do. Nếu record phải được xử lý lại sau khi reference được bổ sung, quarantine store cần giữ thông tin đủ để reprocess.

Nếu missing profile là lỗi cấu hình toàn cục, ví dụ service trỏ nhầm database hoặc bảng reference chưa được nạp, skip từng item sẽ làm mất dữ liệu. Cần fail job sau một ngưỡng nhỏ hoặc kiểm tra dependency trước khi step chạy.

## 18. Validation trước hay sau enrichment?

Thứ tự phụ thuộc dữ liệu cần để validate:

~~~text
Input
  |
  v
Validate structural fields
  |
  v
Enrich reference data
  |
  v
Validate business rules using enriched values
  |
  v
Map output
~~~

Ví dụ customerCode rỗng có thể bị từ chối trước lookup. Nhưng quy tắc “customer tier phải hỗ trợ loại order này” chỉ kiểm tra được sau khi đã tra cứu tier.

Tách validation thành structural validation và business validation giúp tránh query không cần thiết. Nó cũng làm rõ lỗi thiếu field nguồn khác với lỗi reference không tồn tại.

## 19. Kết hợp các processor bằng CompositeItemProcessor

Nếu muốn tách từng bước xử lý, có thể dùng CompositeItemProcessor:

~~~java
@Bean
CompositeItemProcessor<CustomerInput, EnrichedCustomer> customerProcessor(
        ItemProcessor<CustomerInput, CustomerInput> validator,
        ItemProcessor<CustomerInput, CustomerEnrichedData> enricher,
        ItemProcessor<CustomerEnrichedData, EnrichedCustomer> mapper) {

    return new CompositeItemProcessorBuilder<CustomerInput, EnrichedCustomer>()
        .delegates(validator, enricher, mapper)
        .build();
}
~~~

Luồng kiểu dữ liệu:

~~~text
CustomerInput
    |
    v
Validator
    |
    v
CustomerInput
    |
    v
Enricher
    |
    v
CustomerEnrichedData
    |
    v
Mapper
    |
    v
EnrichedCustomer
~~~

Output type của mỗi delegate phải tương thích với input type của delegate tiếp theo. Nếu một delegate trả null, pipeline lọc item và các delegate sau không được gọi cho item đó.

CompositeItemProcessor giúp tách trách nhiệm nhưng không tự tạo transaction riêng cho từng processor. Toàn bộ processor chain vẫn chạy trong xử lý chunk của step.

## 20. Enrichment processor có thể lọc item không?

ItemProcessor được phép trả null. Spring Batch xem đây là filter: item không được chuyển tới writer và được tính vào filter count.

Ví dụ:

~~~java
@Override
public EnrichedCustomer process(CustomerInput input) {
    if (input.isTestRecord()) {
        return null;
    }

    return enrich(input);
}
~~~

Chỉ dùng null để lọc khi việc loại item là một quyết định nghiệp vụ rõ ràng. Không trả null khi lookup thất bại hoặc dữ liệu thiếu mà chưa có policy, vì điều đó khiến item biến mất khỏi output mà không có exception để skip listener xử lý.

Phân biệt:

- Return null: filter item có chủ đích.
- Throw exception: item không xử lý được; step áp dụng retry/skip/fail.
- Return object với trạng thái rejected: writer/quarantine tiếp nhận record để lưu lý do.

## 21. Không ghi dữ liệu trong enrichment processor

Processor nên tập trung vào tính toán, validation và bổ sung thông tin để tạo output. Nếu processor tự ghi database, gửi message hoặc gọi API tạo side effect, những thao tác này xảy ra trước writer và có thể bị lặp khi chunk retry.

Ví dụ không nên:

~~~java
@Override
public EnrichedOrder process(OrderInput input) {
    EnrichedOrder order = enrich(input);
    auditRepository.save(new AuditRecord(order.id()));
    return order;
}
~~~

Nếu writer sau đó thất bại, transaction có thể rollback audit nếu nó cùng transaction manager, nhưng remote side effect hoặc datasource khác có thể đã commit. Khi processor được gọi lại, audit có thể được ghi lần nữa.

Hãy đưa thao tác ghi vào writer hoặc outbox. Nếu cần lookup read-only, dùng service/repository phù hợp và hiểu transaction semantics của nó.

## 22. Transaction và read consistency

Enrichment từ database có thể chạy trong transaction chunk hoặc transaction/service riêng tùy cấu hình. Cần hiểu lookup nhìn thấy dữ liệu tại thời điểm nào.

Ví dụ job đọc order trong một transaction nhưng service tra customer profile bằng một transaction khác. Nếu profile thay đổi giữa hai lần gọi, hai item cùng customer có thể nhận dữ liệu khác nhau.

Các lựa chọn:

- Dùng cùng transaction/isolation phù hợp nếu cần nhìn cùng snapshot trong chunk.
- Dùng business effective date để truy vấn version reference.
- Dùng immutable reference snapshot theo batch.
- Lưu reference version vào output/audit để giải thích kết quả sau này.

Không giả định một transaction chunk tự tạo snapshot nhất quán cho toàn bộ thời gian job. Isolation semantics phụ thuộc database, transaction manager và cách service mở transaction.

## 23. @StepScope cho enrichment theo JobParameters

Một số enrichment phụ thuộc business date, tenant hoặc reference version:

~~~java
@Bean
@StepScope
ItemProcessor<OrderInput, EnrichedOrder> orderEnrichmentProcessor(
        ProductCatalogService catalog,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    LocalDate effectiveDate = LocalDate.parse(businessDate);
    return input -> {
        Product product = catalog.findForTenant(
            tenantId,
            input.productCode(),
            effectiveDate
        );
        return EnrichedOrder.from(input, product, effectiveDate);
    };
}
~~~

JobParameters giúp cùng JobInstance sử dụng cùng tenant và business date khi restart. Không lấy ngày hiện tại bên trong process() nếu ngày đó ảnh hưởng đến kết quả nghiệp vụ.

Nếu processor giữ cache hoặc mutable state theo execution, StepScope giúp cô lập target instance. Tuy nhiên, processor vẫn có thể được gọi đồng thời trong một số cấu hình; state bên trong phải được thiết kế thread-safe.

## 24. Enrichment với reference data lớn

Nếu bảng reference có hàng triệu dòng, preload toàn bộ vào Map có thể gây memory pressure. Các hướng thay thế:

- Query theo nhóm key từ chunk hoặc theo cửa sổ.
- Dùng cache giới hạn kích thước và TTL.
- Đọc reference qua reader riêng rồi xây staging/index phù hợp.
- Join trực tiếp trong query nguồn khi cùng database và query plan hiệu quả.
- Dùng database index theo business key.
- Chia job theo tenant, region hoặc batch range.

Chọn cách làm dựa trên tỷ lệ trùng key. Nếu một triệu input chỉ dùng 1000 customer code khác nhau, cache hoặc preload 1000 profile có thể hiệu quả. Nếu mỗi input có một key khác nhau, bulk lookup hoặc join có thể tốt hơn.

Đo số query, cache hit ratio, memory, response time và database load thay vì chọn cache chỉ theo cảm tính.

## 25. Xử lý API rate limit và back pressure

Khi enrichment gọi remote service, tốc độ batch có thể vượt khả năng tiếp nhận của API. Các dấu hiệu:

- HTTP 429.
- Timeout tăng.
- Queue request tăng.
- Service trả 503 hoặc throttling response.

Cần áp dụng:

- Connection/read timeout hợp lý.
- Retry có giới hạn và backoff theo hợp đồng dịch vụ.
- Rate limiter hoặc giới hạn concurrency.
- Bulk endpoint nếu API hỗ trợ.
- Cache reference ít thay đổi.
- Circuit breaker hoặc cơ chế ngừng gọi tạm thời khi service đang lỗi kéo dài.

Không retry tức thì liên tục khi nhận 429. Tôn trọng Retry-After nếu API cung cấp và giới hạn tổng thời gian step có thể chờ.

Nếu service không đáp ứng SLA, có thể tách enrichment thành job/step riêng hoặc tạo staging queue để kiểm soát tốc độ. Không để một processor đơn giản biến thành nơi chứa mọi logic retry và orchestration.

## 26. Logging và metrics cho enrichment

Enrichment cần quan sát được vì nhiều lỗi chỉ xuất hiện khi dữ liệu nguồn gặp reference bất thường:

- Số item được xử lý.
- Số item được filter.
- Số item thiếu reference.
- Số lookup theo từng nguồn.
- Cache hit/miss ratio.
- Thời gian lookup trung bình và percentile.
- Số lần retry, timeout và lỗi API.
- Số item được quarantine.

Log nên chứa job execution ID, step execution ID, source batch ID và business key. Không log toàn bộ customer profile hoặc payload nhạy cảm nếu không cần.

Với lỗi enrichment, ghi rõ nguồn nào không tìm thấy dữ liệu và khóa tra cứu nào thất bại. Tránh ghi thông tin bí mật, access token hoặc toàn bộ response của remote service.

## 27. Kiểm thử unit cho enrichment processor

Processor nên được kiểm thử độc lập bằng mock service/repository:

~~~java
@Test
void enrichesCustomerWithProfileAndRegion() {
    when(customerProfiles.findByCode("C-100"))
        .thenReturn(Optional.of(
            new CustomerProfile("C-100", "Example Trading", "GOLD")
        ));
    when(regions.findByCode("SOUTH"))
        .thenReturn(Optional.of(
            new Region("SOUTH", "Southern Region")
        ));

    EnrichedCustomer result =
        processor.process(new CustomerInput("C-100", "SOUTH"));

    assertThat(result.customerName()).isEqualTo("Example Trading");
    assertThat(result.customerTier()).isEqualTo("GOLD");
    assertThat(result.regionName()).isEqualTo("Southern Region");
}
~~~

Unit test nên bao phủ:

- Lookup thành công.
- Customer hoặc reference không tồn tại.
- Input thiếu key bắt buộc.
- Giá trị default theo contract.
- Business date/tenant được truyền đúng.
- Cache hit không gọi repository lần nữa nếu có cache.
- Lỗi transient được truyền ra để step retry.
- Processor không sửa input nếu dùng immutable output.

Không chỉ kiểm tra output; verify số lần service được gọi để phát hiện vô tình tạo N+1 lookup trong code.

## 28. Kiểm thử missing reference và skip

Nếu missing profile được cấu hình skip, integration test cần chạy cả step:

1. Chuẩn bị hai customer có profile và một customer không có profile.
2. Reader trả cả ba input.
3. Enrichment processor ném MissingCustomerProfileException cho item thiếu.
4. Step cấu hình skip exception với limit phù hợp.
5. SkipListener ghi nhận business key của item lỗi.
6. Writer chỉ nhận các item enrich thành công.

Kiểm tra:

- Job/step status đúng.
- Write count bằng số item hợp lệ.
- Skip count bằng số item bị bỏ qua.
- Dữ liệu đích có đủ customer hợp lệ.
- Quarantine/audit lưu được lý do và source reference.

Nếu thiếu reference là lỗi toàn bộ batch, test trường hợp job fail và xác nhận không có dữ liệu được coi là hoàn tất sai.

## 29. Kiểm thử retry cho remote enrichment

Dùng mock server hoặc stub client để mô phỏng:

~~~text
Request 1 -> HTTP 503
Request 2 -> HTTP 503
Request 3 -> HTTP 200 with profile
~~~

Xác nhận:

- Retry count đúng giới hạn.
- Request timeout được áp dụng.
- Thành công cuối cùng tạo đúng enriched item.
- Khi vượt retry limit, step fail hoặc xử lý theo policy.
- Không tạo side effect trùng nếu endpoint không thuần read-only.

Nếu API trả 404, test riêng xem đó là missing reference có thể skip hay lỗi cần fail. Không gom 404 và 503 vào cùng exception type nếu policy khác nhau.

## 30. Kiểm thử cache và tính nhất quán

Với cache, test các trường hợp:

- Cùng key được tra nhiều lần nhưng repository chỉ được gọi theo cache policy.
- Hai tenant có cùng customer code nhưng dữ liệu khác nhau không dùng chung cache entry.
- Cache hết hạn hoặc được refresh theo policy.
- Nhiều thread tra cùng key không tạo kết quả sai.
- Cache được giải phóng sau StepExecution nếu là step-scoped.
- Restart dùng reference version đúng theo business date.

Nếu cache snapshot được preload ở beforeStep, kiểm tra processor không chạy trước khi preload hoàn tất. Với partitioning, xác nhận mỗi partition có đúng lookup scope và không ghi đè map của partition khác.

## 31. Restart và enrichment result

Spring Batch có thể đọc lại item chưa commit sau restart. Nếu enrichment được tính lại, kết quả có thể khác nếu reference data thay đổi.

Ví dụ:

~~~text
Lần chạy đầu:
  Order 100 -> lookup tax rate 8%
  Chunk commit đến Order 90
  Job thất bại trước khi Order 100 được commit

Trước khi restart:
  Tax rate đổi thành 10%

Restart:
  Order 100 được enrich lại với tax rate 10%
~~~

Kết quả có thể không nhất quán trong cùng batch nếu các item trước dùng 8% và item sau restart dùng 10%.

Để tránh:

- Truy vấn tax rate theo effective date cố định.
- Truyền reference version/snapshot ID trong identifying parameters.
- Lưu enrichment decision nếu cần tái sử dụng chính xác.
- Đưa reference data vào staging snapshot trước khi xử lý.

Nếu nghiệp vụ cho phép dùng reference mới khi restart, ghi nhận rõ version/time của reference để audit. Không để hành vi thay đổi âm thầm.

## 32. Restart và cache trong memory

Cache trong memory không tồn tại sau khi process restart. Không dùng cache như checkpoint. Sau restart, cache có thể được nạp lại, nhưng phải nạp đúng reference version và phạm vi dữ liệu của JobInstance cũ.

Nếu cache được preload từ database hiện tại mà không có version/cutoff, restart có thể tạo kết quả khác. Hãy lưu snapshot ID hoặc query theo effective date.

Không lưu toàn bộ cache map vào ExecutionContext nếu map lớn. ExecutionContext dành cho metadata checkpoint nhỏ, serialize được; staging table hoặc reference snapshot là nơi phù hợp hơn cho dữ liệu lớn.

## 33. Enrichment và partitioning

Khi step chạy song song theo partition, processor có thể được gọi trên nhiều thread hoặc worker. Cần xác định:

- Lookup service có thread-safe không?
- Cache dùng chung hay riêng từng partition?
- Rate limit remote API áp dụng toàn job hay từng worker?
- Reference snapshot có nhất quán giữa partition không?
- Có thể cùng một customer key được lookup ở nhiều partition không?

Nếu dùng cache chung, cần thread-safe và có key đầy đủ tenant/version. Nếu dùng cache riêng, có thể tăng số lần lookup nhưng dễ cô lập hơn.

Đối với remote service, giới hạn concurrency toàn job để không nhân số request lên theo số partition. Một rate limiter riêng mỗi partition có thể khiến tổng tốc độ vượt giới hạn API.

## 34. Enrichment bằng query join thay vì processor lookup

Nếu dữ liệu chính và reference nằm trong cùng database, có thể lấy thông tin enrich ngay trong reader query:

~~~sql
select new com.example.EnrichedCustomer(
    c.customerCode,
    c.name,
    r.regionName,
    t.tierName
)
from Customer c
left join Region r on r.code = c.regionCode
left join CustomerTier t on t.code = c.tierCode
where c.status = :status
order by c.id
~~~

Ưu điểm:

- Giảm số query per item.
- Database tối ưu join và index.
- Reader trả sẵn projection cần thiết.
- Không cần giữ entity graph lớn trong processor.

Nhược điểm:

- Query có thể phức tạp.
- Join có thể tạo duplicate row nếu quan hệ không duy nhất.
- Pagination cần được kiểm tra kỹ.
- Logic enrichment gắn chặt với database query.
- Khó kết hợp nguồn ngoài database.

Nếu query join làm reader khó bảo trì hoặc cần gọi remote service, giữ enrichment ở processor/service có thể phù hợp hơn.

## 35. Các lỗi thường gặp khi dùng enrichment processor

**Query một lần cho mỗi item:** tạo N+1 lookup và tăng tải database. Dùng join, bulk lookup hoặc cache phù hợp.

**Preload toàn bộ reference không giới hạn:** có thể gây memory pressure. Đo kích thước và chọn cache có giới hạn hoặc lookup theo nhóm.

**Cache không có tenant/version trong key:** có thể trả nhầm dữ liệu giữa tenant hoặc business date. Dùng cache key đầy đủ.

**Dùng ngày hiện tại trong processor:** restart ngày khác có thể tạo output khác. Truyền business date qua JobParameters.

**Gộp missing reference với lỗi kết nối:** 404 và 503 có ý nghĩa khác nhau. Dùng exception/result type riêng.

**Skip mọi lỗi enrichment:** có thể bỏ qua lỗi hạ tầng và làm mất dữ liệu. Chỉ skip lỗi record được nghiệp vụ cho phép.

**Retry mọi RuntimeException:** lỗi mapping hoặc reference cố định sẽ lặp vô ích. Retry lỗi transient có giới hạn.

**Trả null khi lookup thất bại:** item bị filter âm thầm. Dùng exception hoặc quarantine theo policy.

**Ghi dữ liệu trong processor:** side effect có thể lặp khi retry/rollback. Đưa thao tác ghi vào writer hoặc outbox.

**Truy cập lazy association sau khi entity detached:** có thể gây LazyInitializationException. Dùng fetch strategy hoặc projection phù hợp.

**Giữ cache mutable trong singleton dùng chung:** các job/partition có thể ghi đè state. Dùng scope và concurrency model phù hợp.

**Không kiểm tra restart với reference thay đổi:** cùng item có thể được enrich khác sau restart. Cố định reference version hoặc ghi nhận quyết định.

**Chỉ test processor bằng mock:** không phát hiện N+1, transaction, rate limit hoặc restart issue. Thêm integration/performance test phù hợp.

## 36. Quy trình thiết kế enrichment processor trong production

Trước tiên, xác định dữ liệu nào cần được bổ sung, nguồn nào sở hữu dữ liệu đó và mốc thời gian/version dùng để tra cứu. Kiểm tra input bắt buộc trước khi lookup; dùng output model rõ ràng để phân biệt source field và enriched field. Chọn giữa query join, bulk lookup, preload và cache theo kích thước dữ liệu cùng tần suất trùng key.

Tiếp theo, triển khai processor stateless hoặc giữ state theo StepExecution có kiểm soát. Dùng service/repository cho lookup, đặt timeout cho remote call, phân loại missing reference và lỗi transient bằng exception/result type riêng. Không tạo side effect ghi trong processor. Cấu hình retry cho lỗi có khả năng phục hồi, skip/quarantine cho lỗi record được phép bỏ qua và fail cho lỗi cấu hình/hạ tầng nghiêm trọng.

Cuối cùng, kiểm thử lookup thành công, missing reference, cache, tenant isolation, business date, retry, skip, restart và concurrency. Đo số query/request, latency, cache hit ratio và memory khi chạy dữ liệu lớn. Nếu kết quả enrichment phải giữ nguyên qua restart, cố định reference snapshot/version hoặc lưu decision cần thiết trong dữ liệu bền vững.

Enrichment processor bổ sung dữ liệu để item có đủ thông tin cho các bước xử lý và ghi tiếp theo. Một thiết kế tốt tách rõ validation, lookup và mapping; tránh N+1 query; kiểm soát cache và reference version; đồng thời phân loại missing data khác với lỗi hạ tầng. Khi processor không tạo side effect, query và parameters ổn định, writer idempotent và integration test bao phủ restart, batch có thể enrich dữ liệu hiệu quả mà vẫn giữ được khả năng phục hồi và audit.
