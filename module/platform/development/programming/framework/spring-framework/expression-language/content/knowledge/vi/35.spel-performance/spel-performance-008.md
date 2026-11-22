# Cache expression theo nguồn và vòng đời cấu hình

## Mục tiêu

Parse một SpEL expression tạo ra một đối tượng **Expression** có thể được dùng cho nhiều lần đánh giá. Nếu ứng dụng thường xuyên đánh giá cùng một rule, việc parse lại chuỗi mỗi lần tạo thêm chi phí không cần thiết. Có thể cache Expression đã parse theo nguồn biểu thức và cấu hình parser để tái sử dụng.

Cache cần phản ánh đúng vòng đời của rule và cấu hình. Khi source expression, ParserContext, compiler mode hoặc class loader thay đổi, entry cũ có thể không còn phù hợp. Đồng thời, cần tách Expression khỏi EvaluationContext: Expression mô tả logic đã parse, còn EvaluationContext chứa root object, biến và dữ liệu của lần đánh giá. Cache nhầm context hoặc kết quả có thể giữ state cũ và làm lẫn dữ liệu giữa request.

Sau bài này, bạn có thể:

- Phân biệt parse, evaluate và cache kết quả.
- Cache Expression theo source, phiên bản rule và cấu hình parser.
- Dùng cache có giới hạn dung lượng và chính sách eviction.
- Invalidate expression khi nội dung hoặc cấu hình thay đổi.
- Tách vòng đời Expression khỏi EvaluationContext và root object.
- Hiểu ảnh hưởng của compiler mode và class loader tới cache.
- Tránh cache expression không đáng tin cậy không giới hạn.
- Kiểm thử cache hit, cache miss, invalidation, concurrency và stale state.

## 1. Vì sao cache Expression?

Khi gọi parseExpression(), SpEL phân tích source text và tạo cấu trúc Expression. Nếu ứng dụng parse cùng một chuỗi trong mọi request, công việc parse được lặp lại dù logic không đổi.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#root.total >= #minimumTotal");
~~~

Nếu rule được dùng cho hàng nghìn request, có thể giữ lại Expression sau lần parse đầu tiên rồi đánh giá lại nó với root object và biến mới.

~~~java
Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Cache Expression có thể giảm chi phí parse và giúp tập trung quản lý rule. Nó không tự làm cho quá trình evaluate nhanh hơn trong mọi trường hợp; chi phí truy cập property, gọi method, conversion và xử lý dữ liệu vẫn còn. Nếu dùng compiler, lợi ích và điều kiện biên dịch là một vấn đề riêng cần đo lường.

Cache phù hợp khi:

- Cùng một source expression được đánh giá nhiều lần.
- Rule có ID hoặc version ổn định.
- Parser configuration được quản lý rõ.
- Có thể xác định thời điểm cập nhật và loại bỏ expression cũ.
- Số lượng rule được kiểm soát hoặc cache có giới hạn.

Nếu mỗi request tạo một expression hoàn toàn khác, cache có thể không có hit rate tốt và còn giữ nhiều object không cần thiết.

## 2. Phân biệt parse, evaluate và cache kết quả

Ba thao tác có vòng đời khác nhau:

| Thành phần | Nội dung | Vòng đời thường phù hợp |
|---|---|---|
| Source expression | Chuỗi SpEL được lưu trong rule/configuration | Theo phiên bản rule |
| Parsed Expression | Cấu trúc expression đã parse, có thể có compiled state | Cache theo source và parser configuration |
| EvaluationContext | Root object, biến và resolver/accessor của một lần đánh giá | Theo request hoặc lần đánh giá |
| Evaluation result | Giá trị trả về cho một input cụ thể | Chỉ cache nếu đã xác định đầy đủ mọi dependency |

Ví dụ expression:

~~~text
#root.total >= #minimumTotal
~~~

Source có thể không đổi trong nhiều tháng. Parsed Expression có thể được tái sử dụng. Nhưng mỗi request có thể có một Order khác nhau và minimumTotal khác nhau, vì vậy context phải phản ánh đúng dữ liệu của request hiện tại.

Không nên coi cache Expression là cache kết quả. Cùng một expression có thể trả true cho request này và false cho request khác.

Cũng không nên cache một EvaluationContext chứa root object hoặc biến của request rồi dùng lại cho request kế tiếp. Context có thể giữ tham chiếu và state mutable, gây stale data hoặc rò rỉ dữ liệu giữa request.

## 3. Thiết kế cache key

Cache key phải xác định duy nhất một expression trong đúng ngữ cảnh parse. Chỉ dùng tên rule có thể không đủ nếu nội dung rule được chỉnh sửa nhưng key không đổi.

Một cache key có thể bao gồm:

- Rule ID hoặc tên logic.
- Version hoặc revision của rule.
- Source expression chính xác hoặc hash của source.
- ParserContext, gồm chế độ template và cặp prefix/suffix nếu có.
- Các tùy chọn SpelParserConfiguration ảnh hưởng tới cách parse/evaluate.
- Compiler mode và compiler class loader nếu chúng thuộc cấu hình expression.
- Phiên bản hoặc fingerprint của cấu hình parser do ứng dụng quản lý.

Ví dụ, cùng một chuỗi có thể được parse theo hai cách khác nhau:

~~~java
parser.parseExpression(source);
~~~

và:

~~~java
parser.parseExpression(source, new TemplateParserContext());
~~~

Cách thứ hai dùng template ParserContext. Không được lấy Expression đã parse theo chế độ thường rồi dùng thay cho template expression chỉ vì source text giống nhau.

Nếu ứng dụng hỗ trợ delimiter tùy chỉnh, prefix/suffix cần thuộc key. Tương tự, khi compiler mode hoặc class loader thay đổi, hãy tạo một cache namespace mới hoặc invalidate những expression được tạo theo cấu hình cũ.

Có thể dùng rule ID cộng version làm key nếu version được tăng chắc chắn mỗi khi source hoặc parser configuration thay đổi. Nếu không có cơ chế version đáng tin cậy, hãy đưa source hoặc hash source vào key.

## 4. Ví dụ cache Expression đơn giản

Với tập rule nhỏ và được kiểm soát, ConcurrentHashMap có thể làm cache cơ bản:

~~~java
public class SpelExpressionRegistry {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    private final ConcurrentMap<String, Expression> cache =
        new ConcurrentHashMap<>();

    public Expression get(String ruleVersion, String source) {
        String key = ruleVersion + ":" + source;

        return cache.computeIfAbsent(
            key,
            ignored -> parser.parseExpression(source)
        );
    }
}
~~~

computeIfAbsent chỉ tạo giá trị khi key chưa có trong map. Nếu source không đổi và key giống nhau, ứng dụng nhận lại Expression đã parse.

Đây là ví dụ minh họa cho cache nhỏ. Trong ứng dụng thực tế, key nên là một kiểu dữ liệu riêng thay vì nối chuỗi tùy tiện, và cần tính tới ParserContext cùng parser configuration.

Ví dụ key có cấu trúc:

~~~java
public record ExpressionKey(
    String ruleId,
    long ruleVersion,
    String source,
    String parserContextId,
    String parserConfigurationId
) {}
~~~

Registry có thể dùng ExpressionKey làm key của ConcurrentMap. Trường parserConfigurationId là fingerprint do ứng dụng tạo từ các tùy chọn liên quan; không nên dựa vào toString() của một configuration object nếu nó không được thiết kế làm định danh ổn định.

Nếu dự án dùng Java trước phiên bản hỗ trợ record, hãy tạo class immutable có equals() và hashCode() tương ứng.

## 5. Dùng cache có giới hạn dung lượng

ConcurrentHashMap không tự giới hạn số entry. Nếu rule source đến từ người dùng hoặc được tạo liên tục, map có thể tăng không giới hạn và giữ Expression cùng các object liên quan trong bộ nhớ.

Với hệ thống có nhiều rule hoặc source thay đổi, hãy dùng bounded cache có chính sách eviction. Ví dụ, Caffeine hỗ trợ giới hạn số entry:

~~~java
Cache<ExpressionKey, Expression> cache =
    Caffeine.newBuilder()
        .maximumSize(2_000)
        .build();
~~~

Lấy hoặc tạo expression:

~~~java
Expression expression = cache.get(
    key,
    ignored -> parser.parseExpression(source, parserContext)
);
~~~

Giới hạn 2.000 chỉ là giá trị minh họa. Hãy chọn maximumSize theo số lượng rule hoạt động, kích thước expression, heap budget và số instance của ứng dụng.

Các chính sách thường cần cân nhắc:

- Maximum size để giới hạn số expression được giữ.
- Expiration sau thời gian không truy cập nếu rule có tính tạm thời.
- Invalidation rõ ràng khi rule thay đổi.
- Thống kê hit, miss, eviction và parse failure.
- Giới hạn độ dài source và tốc độ tạo rule mới.
- Tách cache theo tenant hoặc namespace nếu rule có phạm vi khác nhau.

Không nhất thiết phải dùng thư viện cache ngoài nếu số rule nhỏ, cố định và được nạp khi khởi động. Nhưng nếu dùng map không giới hạn, phải có giới hạn nguồn rule và vòng đời rõ ràng.

## 6. Cache miss, cache hit và parse failure

Một cache miss xảy ra khi key chưa có entry. Ứng dụng parse source, sau đó lưu Expression nếu parse thành công.

Cache hit xảy ra khi key đã tồn tại. Ứng dụng lấy Expression đã parse và chuyển thẳng sang bước evaluate.

Nếu source có cú pháp sai, parseExpression() ném exception. Hãy quyết định chính sách với parse failure:

- Báo lỗi cấu hình và không kích hoạt rule.
- Ghi nhận rule ID, version và vị trí parse error.
- Không đưa một Expression không hợp lệ vào cache như thể parse thành công.
- Có thể lưu trạng thái validation/error riêng nếu ứng dụng cần tránh parse lặp lại một rule lỗi, nhưng phải gắn với đúng version và có chính sách invalidation.

Không nên giữ một lỗi parse vô thời hạn nếu source có thể được sửa. Khi version mới được phát hành, trạng thái lỗi của version cũ không được ngăn rule mới được parse.

## 7. Invalidation khi source hoặc rule thay đổi

Cache chỉ đúng khi entry còn tương ứng với source và configuration hiện hành.

Các sự kiện cần invalidation:

- Nội dung expression được chỉnh sửa.
- Rule bị xóa hoặc vô hiệu hóa.
- Version rule được thay đổi.
- ParserContext hoặc delimiter thay đổi.
- SpelParserConfiguration thay đổi.
- Compiler mode hoặc compiler class loader thay đổi.
- Ứng dụng reload module hoặc class loader.
- Tenant hoặc namespace thay đổi phạm vi sở hữu rule.

Có hai chiến lược phổ biến.

### Versioned key

Mỗi lần rule thay đổi, tăng version. Key mới tạo entry mới; entry version cũ có thể bị eviction sau đó.

Ưu điểm là request đang dùng version cũ có thể hoàn tất bằng expression cũ trong khi request mới dùng version mới, nếu hệ thống cho phép hai version cùng tồn tại.

### Explicit invalidation

Khi rule thay đổi, gọi invalidate(key) hoặc invalidateAll() cho namespace liên quan. Cách này giải phóng entry cũ sớm hơn nhưng cần phối hợp với request đang đánh giá và chính sách deploy.

Không cập nhật nội dung một expression cache entry tại chỗ theo cách không rõ ràng. Hãy tạo key/version mới hoặc invalidate rồi parse lại để mỗi request biết nó đang dùng rule revision nào.

## 8. Vòng đời cấu hình parser

Expression được tạo ra bởi một parser với cấu hình cụ thể. Parser configuration có thể bao gồm:

- Compiler mode.
- Compiler class loader.
- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- ParserContext và delimiter của template.
- Các tùy chọn khác của phiên bản Spring đang dùng.

Nếu ứng dụng có nhiều bộ cấu hình parser, nên dùng registry/cache riêng cho từng bộ cấu hình hoặc đưa fingerprint cấu hình vào key. Không lấy Expression từ cache tạo bằng parser này rồi dùng như thể nó chắc chắn tương đương với Expression parse bằng parser khác.

Ví dụ cấu hình compiler:

~~~java
SpelParserConfiguration configuration =
    SpelParserConfiguration.builder()
        .compilerMode(SpelCompilerMode.MIXED)
        .build();

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Khi compiler mode thay đổi, hãy xem đó là thay đổi cấu hình có thể yêu cầu cache namespace mới hoặc invalidation. Compiled state thuộc về Expression đã parse và có thể chịu ảnh hưởng của compiler class loader cùng kiểu runtime quan sát được.

Cấu hình parser nên được tạo tập trung, có version hoặc fingerprint rõ ràng và không thay đổi âm thầm trong khi cache đang hoạt động.

## 9. Compiler và vòng đời Expression

Một Expression có thể chứa trạng thái compilation khi compiler được bật. Compiler học kiểu runtime từ các lần interpreted evaluation và có thể tạo bytecode cho những expression được hỗ trợ.

Điều này ảnh hưởng tới cách quản lý cache:

- Cache entry có thể giữ một Expression đã có compiled state.
- Thay đổi compiler mode không tự biến Expression cũ thành Expression mới với cấu hình khác.
- Thay class loader hoặc unload module có thể làm compiled expression cũ không còn phù hợp.
- Thay đổi kiểu runtime có thể khiến compiled form thất bại theo mode đã chọn.
- MIXED có thể quay lại interpreted mode sau lỗi compiled evaluation.

Nếu class loader gắn với plugin hoặc module có thể bị unload, hãy invalidate expression phụ thuộc vào class loader đó trước khi giải phóng module. Nếu không, cache có thể giữ tham chiếu làm class loader và class cũ không được thu hồi.

Đừng dùng cache Expression để che giấu vấn đề type instability. Hãy kiểm thử cùng expression với các kiểu runtime thực tế và chọn compiler mode phù hợp.

## 10. Tách EvaluationContext khỏi cache

EvaluationContext chứa root object, biến và các resolver/accessor. Đây thường là state của một lần đánh giá.

Ví dụ đúng về vòng đời:

~~~java
Expression expression = expressionRegistry.get(key, source);

StandardEvaluationContext context =
    new StandardEvaluationContext(currentOrder);

context.setVariable("minimumTotal", currentMinimum);

Boolean result =
    expression.getValue(context, Boolean.class);
~~~

Expression được lấy từ cache. Context mới được tạo với Order và minimumTotal của request hiện tại.

Tránh thiết kế như sau:

~~~java
// Không giữ context chứa request data trong singleton cache.
sharedContext.setRootObject(currentOrder);
sharedContext.setVariable("minimumTotal", currentMinimum);
~~~

Nếu nhiều request cùng thay root object hoặc biến trên một context, một lần đánh giá có thể đọc state của request khác. Context còn có thể giữ tham chiếu tới entity, collection hoặc object lớn lâu hơn cần thiết.

Có thể tái sử dụng một context trong một luồng tuần tự nếu root object và biến thực sự ổn định, nhưng phải có ownership và vòng đời rõ. Với request độc lập, context riêng thường an toàn và dễ kiểm thử hơn.

## 11. Không cache kết quả nếu dependency chưa được xác định

Cache kết quả là một bài toán khác với cache Expression. Kết quả có thể phụ thuộc vào:

- Root object và property mutable.
- Biến context.
- Bean được tham chiếu.
- Thời gian hiện tại.
- Locale, timezone và cấu hình môi trường.
- User, tenant hoặc security context.
- Dữ liệu database hoặc service được method gọi tới.
- ConversionService và custom function.
- Phiên bản rule.

Ví dụ expression:

~~~text
#root.total >= #minimumTotal
~~~

Nếu cache kết quả chỉ theo rule ID, request khác có thể nhận Boolean được tính từ Order hoặc ngưỡng của request trước.

Chỉ cache kết quả khi đã xác định đầy đủ input key, mọi dependency có ảnh hưởng và thời hạn hợp lệ. Nếu expression đọc state thay đổi hoặc gọi method có side effect, cache kết quả có thể làm sai nghiệp vụ.

Trong nhiều ứng dụng, cache parsed Expression là đủ; evaluation vẫn chạy với context và dữ liệu hiện tại.

## 12. Cấu hình và bảo mật khi cache expression

Cache không làm source expression trở nên an toàn. Một expression được parse từ nguồn không đáng tin vẫn có thể gọi các khả năng mà EvaluationContext cho phép.

Các nguyên tắc:

- Chỉ parse expression từ nguồn được xác thực và có quyền cấu hình.
- Dùng EvaluationContext với quyền tối thiểu cần thiết.
- Giới hạn property accessor, method resolver, type locator, bean resolver và function được cung cấp.
- Giới hạn độ dài source và số lượng rule.
- Dùng bounded cache để tránh tiêu thụ heap không giới hạn.
- Không log source nếu nó có thể chứa secret hoặc dữ liệu riêng tư.
- Phân tách cache theo tenant nếu rule và quyền sở hữu không dùng chung.
- Không dùng cache key do client tự chọn mà không kiểm tra quyền truy cập rule.
- Version hóa rule và ghi nhận version khi evaluate để truy vết.
- Invalidate entry khi quyền, source hoặc configuration thay đổi.

Một cache key duy nhất không phải cơ chế phân quyền. Trước khi lấy expression, ứng dụng vẫn cần xác minh caller được phép dùng rule đó.

## 13. Quan sát cache và vận hành

Để biết cache có đem lại lợi ích, cần theo dõi cả hit rate lẫn chi phí parse/evaluate.

Các chỉ số hữu ích:

- Cache hit count và miss count.
- Hit ratio theo rule group hoặc namespace.
- Parse duration và parse failure count.
- Số entry hiện tại và số lần eviction.
- Kích thước source hoặc phân bố độ dài expression.
- Số rule invalidation và lý do invalidation.
- Evaluation duration riêng với parse duration.
- Compiler mode và lỗi compiled evaluation nếu compiler được bật.

Không gộp parse time với evaluate time. Nếu evaluate chiếm gần như toàn bộ thời gian, cache parse có thể không tạo khác biệt lớn.

Khi cache miss tăng đột biến, kiểm tra rule version có bị thay đổi liên tục, key có chứa giá trị request ngoài ý muốn hoặc cache quá nhỏ không. Nếu entry bị eviction thường xuyên, cân nhắc tăng giới hạn sau khi đo heap và workload.

Khi deploy phiên bản ứng dụng mới, xác định cache có nằm trong memory của từng instance hay được chia sẻ ngoài tiến trình. Với in-memory cache, mỗi instance có thể có entry riêng và cần nạp/invalidate nhất quán theo version rule.

## 14. Kiểm thử cache và vòng đời cấu hình

Một bộ test cần xác nhận cache trả đúng Expression, không tái sử dụng context cũ và invalidation hoạt động.

### Cache hit và miss

~~~java
@Test
void reusesParsedExpressionForSameKey() {
    Expression first = registry.get(key, source);
    Expression second = registry.get(key, source);

    assertSame(first, second);
}
~~~

Test này chỉ phù hợp khi registry được thiết kế để trả lại cùng instance trong cache. Nếu cache implementation không cam kết identity, hãy kiểm tra số lần parser được gọi hoặc metrics hit/miss thay vì assertSame.

### Source version thay đổi

~~~java
Expression versionOne =
    registry.get(keyForVersionOne, "1 + 2");

Expression versionTwo =
    registry.get(keyForVersionTwo, "1 + 3");

assertEquals(3, versionOne.getValue());
assertEquals(4, versionTwo.getValue());
~~~

Hai version không được vô tình dùng chung expression nếu source khác nhau.

### Context riêng cho từng lần đánh giá

~~~java
Expression expression =
    registry.get(ruleKey, "#root.total >= #minimumTotal");

StandardEvaluationContext first =
    new StandardEvaluationContext(orderA);
first.setVariable("minimumTotal", new BigDecimal("100"));

StandardEvaluationContext second =
    new StandardEvaluationContext(orderB);
second.setVariable("minimumTotal", new BigDecimal("500"));

Boolean firstResult =
    expression.getValue(first, Boolean.class);

Boolean secondResult =
    expression.getValue(second, Boolean.class);
~~~

Cùng Expression được dùng với hai context độc lập. Test cần xác nhận mỗi kết quả phụ thuộc đúng root object và biến tương ứng.

Các trường hợp nên kiểm tra:

- Cache miss parse thành công.
- Cache hit dùng lại expression.
- Source thay đổi nhưng rule ID giữ nguyên.
- Version rule thay đổi.
- ParserContext hoặc delimiter thay đổi.
- Compiler mode hoặc parser configuration thay đổi.
- Parse failure không được coi là entry hợp lệ.
- Invalidation xóa đúng key/namespace.
- Eviction không làm thay đổi kết quả evaluate.
- Hai request song song dùng context riêng.
- Cache không giữ root object hoặc biến của request.
- Plugin/class loader được unload thì expression phụ thuộc được invalidate.
- Cache có giới hạn khi source mới liên tục xuất hiện.

## 15. Quy trình triển khai cache

1. **Xác định nguồn rule.** Chọn rule ID, version và nơi lưu source expression.
2. **Định nghĩa parser configuration.** Cố định compiler mode, ParserContext, delimiter, class loader và các tùy chọn liên quan.
3. **Thiết kế key.** Đưa source/version và parser configuration identity vào key.
4. **Chọn cache policy.** Xác định maximum size, expiration và namespace.
5. **Parse khi miss.** Chỉ cache Expression nếu parse thành công.
6. **Tạo context khi evaluate.** Đặt root object và biến của request hiện tại.
7. **Theo dõi version.** Ghi nhận rule version được dùng cho lần đánh giá.
8. **Invalidate khi thay đổi.** Loại entry cũ khi source, permission hoặc configuration thay đổi.
9. **Đo hiệu năng.** Tách parse duration, cache lookup và evaluate duration.
10. **Kiểm thử isolation.** Xác nhận context và kết quả không bị lẫn giữa request.

## 16. Thực hành tốt

- Cache parsed Expression khi cùng source được dùng lặp lại.
- Xây cache key từ rule ID/version, source và parser configuration.
- Đưa ParserContext và delimiter vào key khi chúng ảnh hưởng parsing.
- Tạo parser configuration ổn định và quản lý theo version.
- Dùng bounded cache cho tập rule có thể tăng theo thời gian.
- Invalidate hoặc version hóa entry khi rule thay đổi.
- Không cache EvaluationContext chứa root object hoặc biến của request.
- Không cache evaluation result nếu chưa xác định đầy đủ dependency.
- Tạo context riêng cho request hoặc lần đánh giá độc lập.
- Kiểm soát source expression và quyền truy cập trước khi parse/evaluate.
- Theo dõi hit, miss, eviction, parse failure và evaluate duration.
- Xử lý class loader/plugin lifecycle để cache không giữ class cũ.
- Đo hiệu năng thực tế trước khi tăng độ phức tạp của cache.

## 17. Checklist review

Trước khi đưa expression cache vào production, hãy kiểm tra:

- [ ] Cache chỉ lưu Expression đã parse thành công.
- [ ] Cache key phân biệt rule ID và version/source.
- [ ] ParserContext và delimiter được phản ánh trong key.
- [ ] Parser configuration và compiler mode có identity rõ.
- [ ] Class loader được quản lý đúng vòng đời.
- [ ] Cache có maximum size hoặc giới hạn nguồn rule.
- [ ] Có chính sách expiration/eviction phù hợp.
- [ ] Có invalidation khi source hoặc configuration thay đổi.
- [ ] EvaluationContext không bị giữ trong cache dùng chung.
- [ ] Root object và biến thuộc đúng request.
- [ ] Evaluation result không bị cache theo key thiếu dependency.
- [ ] Expression từ nguồn ngoài được xác thực và giới hạn quyền.
- [ ] Có metrics cho hit, miss, parse failure và eviction.
- [ ] Có test cache hit/miss, version change, invalidation và concurrency.
- [ ] Có test xác nhận state không bị lẫn giữa các lần đánh giá.

## Kết luận

Cache Expression giúp tránh parse lặp lại cùng một SpEL source. Cache key cần phản ánh source hoặc version rule cùng ParserContext và cấu hình parser có ảnh hưởng. Khi source, compiler mode, class loader hoặc cấu hình thay đổi, cần tạo version/key mới hoặc invalidate entry cũ. Hãy giữ EvaluationContext và root object theo vòng đời của từng request, không cache kết quả nếu chưa xác định đủ dependency, và dùng bounded cache cùng metrics để kiểm soát bộ nhớ và hiệu năng.