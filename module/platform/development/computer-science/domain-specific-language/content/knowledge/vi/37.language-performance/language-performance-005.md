# Bộ nhớ đệm AST

## Bộ nhớ đệm AST trong hiệu năng DSL là gì?

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường phải phân tích source text thành cấu trúc cú pháp trước khi có thể kiểm tra kiểu, resolve tên, xây dựng kế hoạch hoặc thực thi. Cấu trúc này thường được biểu diễn bằng cây cú pháp trừu tượng (Abstract Syntax Tree, AST).

Quá trình parse có thể tốn CPU và cấp phát nhiều object, đặc biệt khi source DSL lớn, có nhiều module hoặc được sử dụng lặp lại. Trong ứng dụng host, cùng một file rule, query, workflow hoặc template có thể được đánh giá nhiều lần với context khác nhau. Nếu mỗi lần đều đọc và parse lại source không thay đổi, hệ thống sẽ lặp lại công việc không cần thiết.

**Bộ nhớ đệm AST (AST cache)** lưu trữ AST đã được tạo từ source để lần sử dụng sau có thể tái dùng thay vì parse lại. Cache cần xác định chính xác source và các tùy chọn parse đã tạo ra AST, quản lý vòng đời của entry, loại bỏ entry khi dependency thay đổi và giới hạn bộ nhớ sử dụng.

Ví dụ, host application nạp một rule:

~~~text
RULE discount {
  WHEN customer.segment == "VIP"
   AND order.total >= 1000000
  THEN order.total * 0.10
}
~~~

Lần đầu, parser đọc source và tạo AST. Những lần thực thi tiếp theo có thể lấy AST từ cache nếu source, grammar version và parser configuration vẫn tương thích. Runtime vẫn có thể tạo execution context mới, cung cấp customer và order khác nhau, rồi đánh giá cùng AST đó.

AST cache đặc biệt hữu ích khi:

- Một module DSL được nạp và thực thi nhiều lần.
- Nhiều request dùng chung rule hoặc query definition.
- Một host application có nhiều session nhưng cùng một bộ source.
- Language server liên tục xử lý document và request phân tích.
- Workflow engine khởi động lại nhiều process instance từ cùng definition.
- Compiler hoặc interpreter cần giảm thời gian startup và parse.
- Nhiều module import cùng một dependency.
- Source ít thay đổi nhưng số lần sử dụng lớn.

AST cache không làm mọi bước xử lý biến mất. Sau khi lấy AST, hệ thống có thể vẫn cần semantic analysis, type checking, symbol resolution, optimization hoặc compilation. Những kết quả này có dependency khác và thường cần cache riêng.

## AST là gì và vì sao có thể tái sử dụng?

AST là biểu diễn cấu trúc của source sau khi parser đã nhận diện token và quan hệ cú pháp. Nó loại bỏ nhiều chi tiết chỉ phục vụ văn bản, đồng thời giữ lại cấu trúc cần cho các bước sau.

Ví dụ biểu thức:

~~~text
price * quantity + tax
~~~

Có thể được biểu diễn thành:

~~~text
        Add
       /   \
    Multiply  Name(tax)
     /    \
 Name(price) Name(quantity)
~~~

AST thể hiện phép nhân được thực hiện trước phép cộng theo cấu trúc của biểu thức.

### AST thường chứa những gì?

Một AST node có thể chứa:

- Loại node, chẳng hạn BinaryExpression, CallExpression hoặc IfStatement.
- Các node con.
- Identifier hoặc literal value.
- Operator.
- Source span, vị trí bắt đầu và kết thúc trong source.
- Annotation do parser tạo.
- Metadata phục vụ diagnostics hoặc tooling.

Một số hệ thống lưu cả trivia như comment hoặc whitespace trong concrete syntax tree (CST), trong khi AST tập trung vào cấu trúc ngữ nghĩa cú pháp. Cache cần biết chính xác nó đang lưu loại cây nào và các consumer cần metadata nào.

### Vì sao AST có thể được dùng lại?

Nếu source text không thay đổi và parser configuration tương đương, cấu trúc cú pháp tạo ra thường giống nhau. AST không nên chứa dữ liệu thay đổi theo từng lần chạy như:

- User hiện tại.
- Tenant context.
- Database connection.
- Request ID.
- Current transaction.
- Giá trị runtime của biến.
- Kết quả gọi host service.
- Authorization decision theo thời điểm.

Những thông tin này thuộc execution context hoặc semantic/runtime layer. Đưa chúng vào AST dùng chung có thể khiến request sau nhận dữ liệu của request trước hoặc làm cache không thể tái sử dụng an toàn.

### AST bất biến

Một thiết kế phổ biến là AST immutable sau khi parse. Các consumer chỉ đọc node và không sửa trực tiếp cấu trúc dùng chung.

Nếu semantic analysis cần thêm thông tin, có thể tạo một semantic model riêng hoặc lưu annotation trong side table gắn với version. Cách này tránh một request ghi symbol binding vào AST trong khi request khác đang đọc cùng cây.

## Vị trí của AST cache trong pipeline xử lý DSL

AST cache nằm sau bước parse và trước các bước xử lý tiếp theo:

~~~text
DSL source
    |
    v
Source identity and version
    |
    v
AST cache lookup
    |
    +---- cache hit ----> Reuse AST
    |
    +---- cache miss ---> Lexer and parser
                              |
                              v
                         Build AST
                              |
                              v
                         Store AST
    |
    v
Name resolution / semantic analysis
    |
    v
Type checking
    |
    v
Logical plan / compilation
    |
    v
Execution
~~~

Một implementation có thể kết hợp lexing và parsing trong cùng cache pipeline. Một implementation khác có thể cache token stream riêng. Điều quan trọng là cache boundary phải được định nghĩa rõ.

### Parse cache và AST cache

Hai thuật ngữ thường được dùng gần nghĩa nhau, nhưng có thể phân biệt:

- Parse cache lưu kết quả của quá trình parse, thường là AST hoặc syntax tree.
- Token cache lưu token stream đã được lexer tạo.
- AST cache lưu cây cú pháp đã parse, có thể kèm source metadata.
- Semantic cache lưu kết quả resolve symbol, type hoặc module dependency.
- Compiled artifact cache lưu bytecode, execution plan hoặc mã đã biên dịch.

Một cache có thể lưu nhiều lớp dữ liệu, nhưng mỗi lớp cần key và invalidation phù hợp.

### Không cache toàn bộ pipeline bằng một key đơn giản

AST có thể không đổi trong khi schema hoặc host function registry thay đổi. Semantic model có thể cần tính lại. Physical plan có thể thay đổi khi index hoặc backend capability thay đổi. Nếu dùng một cache entry chứa tất cả các lớp mà key chỉ dựa trên source text, hệ thống có thể tái sử dụng kết quả đã lỗi thời.

Nên tách cache theo artifact và dependency của artifact đó, hoặc xây dependency fingerprint bao phủ toàn bộ đầu vào có ảnh hưởng.

## Lợi ích hiệu năng và chi phí của AST cache

AST cache giảm số lần lexer/parser phải làm việc. Mức cải thiện phụ thuộc tỷ lệ cache hit, chi phí parse và chi phí quản lý cache.

### Giảm CPU

Parse một source lớn có thể tạo nhiều node và thực hiện nhiều bước kiểm tra grammar. Nếu source được dùng lặp lại, tái sử dụng AST giúp tránh công việc đó.

### Giảm allocation và garbage collection

Parser thường tạo token, node, list và object phụ trợ. Cache có thể giảm allocation lặp lại, nhưng AST được giữ lâu hơn nên tổng bộ nhớ sống có thể tăng. Vì vậy, cần cân bằng giữa giảm allocation và giữ quá nhiều cây không còn được dùng.

### Giảm latency

Nếu request thường xuyên phải parse cùng một module, cache hit có thể giảm thời gian chuẩn bị trước execution. Tuy nhiên, AST cache không loại bỏ thời gian context construction, semantic analysis hoặc host API calls.

### Giảm startup cost

Host có thể preload một số module quan trọng vào cache trước khi nhận request. Điều này chuyển chi phí parse sang giai đoạn startup hoặc warmup. Cần tránh preload toàn bộ module lớn nếu phần lớn không được sử dụng.

### Chi phí quản lý cache

Cache có chi phí:
- Tính key và kiểm tra dependency.
- Đồng bộ khi nhiều request cùng miss.
- Lưu giữ AST và source metadata.
- Eviction và cleanup.
- Serialization nếu cache persistent.
- Invalidation khi source hoặc grammar thay đổi.
- Metrics và diagnostic.

Nếu DSL nhỏ và mỗi source chỉ được dùng một lần, cache có thể không mang lại lợi ích. Cần đo workload thực tế trước khi chọn chính sách.

## Thiết kế cache key

Cache key xác định AST nào có thể được tái sử dụng. Key quá yếu có thể trả AST sai; key quá rộng có thể làm giảm hit ratio vì các source tương đương không được nhận diện.

Một key khái niệm:

~~~text
AstCacheKey
  sourceIdentity
  contentDigest
  languageVersion
  grammarVersion
  parserOptions
  featureSet
  encoding
~~~

Không phải mọi hệ thống đều cần tất cả trường. Key phải bao gồm mọi yếu tố có thể làm thay đổi cấu trúc AST.

### Source identity

Source identity có thể là:
- Module ID.
- File ID trong workspace.
- URI đã chuẩn hóa.
- Resource ID trong repository.
- Logical name trong module registry.

Identity giúp quản lý entry theo resource và invalidation khi file thay đổi. Tuy nhiên, chỉ dùng path làm key là chưa đủ: nội dung file có thể thay đổi trong khi path không đổi.

### Content hash

Content digest hoặc hash có thể nhận diện source text chính xác. Nếu nội dung giống nhau, hệ thống có thể cân nhắc chia sẻ AST giữa hai resource.

Hash cần được tính từ bytes hoặc text sau một quy tắc chuẩn hóa đã công bố. Nếu parser phân biệt encoding, newline hoặc Unicode normalization, việc chuẩn hóa không đúng có thể khiến key trùng cho source có semantics khác.

Một cách an toàn là hash đúng nội dung đầu vào mà parser thực sự nhận, kèm encoding và parser options liên quan.

### Language và grammar version

Cùng source có thể parse khác khi:
- DSL nâng version.
- Grammar thêm keyword.
- Operator precedence thay đổi.
- Syntax feature được bật hoặc tắt.
- Extension grammar được đăng ký.
- Parser bug được sửa theo cách thay đổi tree.

Do đó, cache key cần nhận diện version hoặc fingerprint của grammar và feature set.

### Parser options

Một số tùy chọn ảnh hưởng AST:
- Strict hoặc permissive mode.
- Macro expansion.
- Feature flags.
- Dialect.
- Case sensitivity.
- Extension registry.
- Error recovery mode.
- Preprocessor definitions.

Nếu hai lần parse dùng options khác nhau, không nên chia sẻ AST trừ khi chứng minh các options không ảnh hưởng cấu trúc.

### Import và include

AST của một file thường chỉ phản ánh cú pháp file đó. Nếu parser mở rộng macro hoặc include trong quá trình parse, dependency content có thể ảnh hưởng AST. Khi đó, cache key cần bao gồm dependency fingerprint hoặc AST phải giữ include node chưa resolve để dependency được xử lý ở semantic layer.

Cần xác định include là thao tác parse-time hay semantic-time. Không nên bỏ qua dependency chỉ vì file gốc không đổi.

### Tránh key dựa trên thời gian sửa file đơn thuần

Modification timestamp có thể có độ phân giải thấp, bị sao chép khi checkout hoặc không được cập nhật đáng tin cậy. Hai nội dung khác nhau có thể có cùng timestamp. Content hash thường đáng tin hơn; timestamp có thể dùng như một heuristic để tránh hash lại khi có cơ chế kiểm chứng bổ sung.

## Cache entry và metadata

Một entry có thể lưu:

~~~text
AstCacheEntry
  key
  ast
  sourceLength
  sourceDigest
  sourceVersion
  parserVersion
  createdAt
  lastAccessedAt
  estimatedSizeBytes
  dependencyFingerprint
  diagnostics
~~~

### AST và source ownership

AST node có thể giữ reference đến source buffer để cung cấp source span hoặc lazy text extraction. Nếu cache giữ AST nhưng không giữ buffer, diagnostics có thể không còn trích được source. Nếu AST giữ toàn bộ buffer, bộ nhớ cache có thể lớn hơn đáng kể.

Cần chọn một trong các cách:
- AST giữ immutable source snapshot.
- AST giữ source ID và span, còn source store quản lý buffer.
- Cache lưu source và AST trong cùng entry với giới hạn size.
- AST chỉ giữ metadata cần thiết, còn source text được lấy từ version store.

### Source version

Với editor hoặc host hỗ trợ reload, mỗi document version cần được phân biệt. AST của version 12 không được trả cho request yêu cầu version 13 nếu source đã thay đổi.

Version có thể là monotonically increasing document version, content digest hoặc repository revision. Không nên dựa vào version number do client cung cấp nếu không có mapping với content thực tế.

### Diagnostics

Parser có thể tạo AST recovery cùng diagnostics cho source chưa hợp lệ. Cần xác định cache có lưu AST lỗi hay không.

Có thể:
- Chỉ cache parse thành công.
- Cache cả AST recovery và diagnostics.
- Cache lỗi parse âm tính trong thời gian ngắn.
- Không cache lỗi phụ thuộc context hoặc dependency chưa sẵn sàng.

Nếu cache diagnostics, source version phải khớp. Khi source thay đổi, diagnostics cũ không được hiển thị như lỗi của version mới.

### Size accounting

Số node không phản ánh chính xác memory footprint vì mỗi node có thể giữ string, list, source buffer và metadata. Có thể ước lượng size theo:
- Số node.
- Số token.
- Tổng kích thước string.
- Source bytes.
- Số collection entry.
- Overhead được đo thực nghiệm theo runtime.

Size accounting không cần chính xác tuyệt đối, nhưng cần nhất quán để giới hạn cache.

## Cache lookup và miss handling

Khi cần AST, loader tạo key và tìm entry.

~~~text
getAst(source, parserConfig):
    key = createKey(source, parserConfig)

    entry = cache.get(key)
    if entry exists:
        return entry.ast

    ast = parser.parse(source, parserConfig)
    cache.put(key, ast)
    return ast
~~~

Đây là mô hình đơn giản. Implementation thực tế cần xử lý đồng thời, lỗi parse, cancellation và invalidation.

### Cache hit

Khi hit, hệ thống cần xác nhận entry vẫn hợp lệ theo version và dependency. Nếu key đã bao gồm mọi dependency bất biến thì lookup có thể đơn giản hơn.

### Cache miss

Khi miss, parser tạo AST mới. Sau parse, cần kiểm tra source version vẫn còn là version được yêu cầu. Nếu source đã đổi trong lúc parse, không nên publish entry dưới key của version mới.

### Cache bypass

Một số trường hợp nên bypass cache:
- Debug mode yêu cầu parse lại để điều tra.
- Parser option không hỗ trợ cache.
- Source quá lớn so với giới hạn.
- Source chứa construct không deterministic theo parser contract.
- Test cần xác nhận parser thực sự được gọi.
- Runtime đang trong quá trình migration hoặc invalidation.

Bypass nên là lựa chọn có chủ đích và được quan sát bằng metric.

### Parse failure

Nếu parse thất bại, cache có thể không lưu entry để tránh giữ lỗi lâu dài. Tuy nhiên, editor có thể liên tục yêu cầu cùng một source chưa hợp lệ; parse lại nhiều lần sẽ tốn CPU. Negative caching có thể giúp, miễn là key gắn với content digest và diagnostics được invalidation đúng.

## Cache invalidation

Invalidation là quá trình làm entry không còn được sử dụng khi một đầu vào có ảnh hưởng thay đổi. Đây là phần quan trọng nhất để tránh cache trả kết quả cũ.

### Invalidate theo source change

Khi file hoặc document thay đổi:
- Tăng source version.
- Tính digest mới.
- Đánh dấu entry cũ không còn current.
- Tạo AST mới khi cần.
- Không cho request mới nhận AST cũ.

Entry cũ có thể vẫn được giữ tạm cho request đang chạy nếu AST immutable. Sau khi không còn consumer, nó có thể được eviction.

### Invalidate theo grammar change

Khi DSL version hoặc grammar thay đổi, entry được tạo bởi parser cũ có thể không còn hợp lệ. Cache namespace theo grammar fingerprint giúp tránh reuse nhầm.

### Invalidate theo parser option

Nếu strict mode, macro setting hoặc extension registry thay đổi, AST có thể khác. Options cần được đưa vào key hoặc trigger invalidation.

### Invalidate dependency

Nếu AST đã expand include hoặc macro, thay đổi dependency có thể làm cây gốc thay đổi. Dependency graph giúp tìm entry cần invalidation.

### Explicit invalidation

API có thể hỗ trợ:
- Invalidate một source ID.
- Invalidate một module.
- Invalidate namespace theo language version.
- Clear cache theo tenant hoặc workspace.
- Invalidate mọi entry phụ thuộc một grammar/plugin version.

Không nên cung cấp clear-all như cách xử lý mặc định cho mọi thay đổi nhỏ vì nó làm mất locality và gây parse spike.

### Invalidation và request đang chạy

Nếu một request đang dùng AST cũ khi source mới được publish, có thể cho request cũ hoàn tất trên snapshot cũ. Request mới phải dùng version mới. Điều này cần version pinning hoặc reference counting để entry cũ không bị giải phóng khi còn consumer.

## Dependency tracking và module graph

DSL thường hỗ trợ module import, include, macro, schema reference hoặc extension. Một AST có thể phụ thuộc vào các file khác nếu preprocessing hoặc parsing mở rộng chúng.

Ví dụ:

~~~text
MODULE checkout {
  IMPORT "common/types.dsl"
  IMPORT "common/expressions.dsl"

  RULE validateOrder {
    ...
  }
}
~~~

Nếu parser inline import vào AST của checkout, thay đổi common/types.dsl phải làm invalidation AST checkout. Nếu import chỉ tạo node tham chiếu, AST của checkout có thể giữ nguyên; semantic dependency hoặc compiled artifact cần được invalidation riêng.

### Dependency fingerprint

Có thể tạo fingerprint từ:
- Source digest của module gốc.
- Danh sách dependency ID.
- Digest/version của từng dependency.
- Grammar và extension version.
- Preprocessor configuration.

Fingerprint nên được tính theo thứ tự canonical để cùng graph tạo cùng key.

### Dependency graph

Cache manager có thể lưu reverse dependency graph:

~~~text
common/types.dsl
       |
       +----> checkout.dsl
       |
       +----> billing.dsl

common/expressions.dsl
       |
       +----> checkout.dsl
~~~

Khi common/types.dsl thay đổi, manager có thể tìm các dependent artifact cần invalidation. Cần phân biệt dependency ảnh hưởng AST với dependency chỉ ảnh hưởng semantic model hoặc compiled plan để tránh invalidation quá rộng.

### Cycle

Import cycle có thể bị cấm hoặc được hỗ trợ theo semantics của DSL. Cache manager không nên đệ quy resolve dependency vô hạn. Graph traversal cần đánh dấu node đang thăm và phát hiện cycle.

## AST cache và incremental parsing

Với editor hoặc language server, source thay đổi thường xuyên theo từng ký tự. Parse lại toàn bộ file sau mỗi keystroke có thể tốn kém.

Incremental parsing cập nhật syntax tree từ một edit range hoặc một tập thay đổi nhỏ. AST cache có thể lưu các version gần nhất hoặc cấu trúc có thể tái sử dụng giữa version.

### Document version

Client có thể gửi didChange với version tăng dần. Server cần áp dụng edit đúng thứ tự và tạo snapshot source tương ứng. AST cache entry phải gắn với version hoặc content digest.

### Reuse subtree

Parser incremental có thể tái sử dụng subtree không bị ảnh hưởng bởi edit. Điều này yêu cầu:
- Source range được cập nhật chính xác.
- Node có cấu trúc immutable hoặc được copy-on-write.
- Parser xác định vùng grammar bị ảnh hưởng.
- Parent/child relation được cập nhật an toàn.
- Diagnostics cũ trong vùng thay đổi được tính lại.

### Edit locality

Một thay đổi trong comment có thể không ảnh hưởng semantic AST nếu DSL bỏ qua comment. Một thay đổi delimiter hoặc keyword có thể ảnh hưởng vùng lớn hơn. Incremental parser cần biết grammar context để xác định phạm vi invalidation.

### Version history

Có thể giữ một số AST version gần nhất để hỗ trợ:
- Request completion đến muộn cho document version cũ.
- Background diagnostics đang chạy.
- Cancellation và retry.
- Compare tree giữa các version.
- Incremental parse tiếp từ version gần nhất.

Không nên giữ vô hạn lịch sử document. Cache cần giới hạn số version hoặc tổng bytes.

### Full parse fallback

Nếu edit không thể áp dụng an toàn, parser nên fallback sang full parse thay vì tạo tree sai. Có thể xảy ra khi:
- Edit range không hợp lệ.
- Version bị thiếu.
- Grammar state bị mất đồng bộ.
- Source encoding thay đổi.
- Parser phát hiện reuse invariant bị vi phạm.

Fallback nên được đếm để nhóm phát triển nhận biết incremental parsing có hiệu quả hay không.

## Concurrency, single-flight và cache stampede

Nhiều request có thể cùng yêu cầu một module chưa có trong cache. Nếu tất cả đều parse độc lập, hệ thống tạo công việc trùng lặp và tăng CPU.

### Single-flight

Single-flight đảm bảo chỉ một computation cho một key đang chạy. Các request khác chờ kết quả chung:

~~~text
Request A ----\
Request B -----+----> Parse key K once ----> Shared AST
Request C ----/
~~~

Sau khi parse thành công, kết quả được publish và các caller nhận cùng entry. Nếu parse thất bại, hệ thống cần quy định caller nhận cùng lỗi hay một caller thử lại.

### Per-key lock

Có thể dùng lock theo key để tránh parse trùng. Tránh một global lock bao quanh toàn bộ cache vì các module độc lập sẽ chặn nhau.

### Promise/future cache

Một cách khác là lưu future của computation đang chạy. Request sau lấy cùng future thay vì bắt đầu parse mới.

Cần xử lý:
- Future thất bại.
- Caller bị cancellation.
- Computation bị timeout.
- Invalidation xảy ra khi parse đang chạy.
- Source version thay đổi trước khi publish.
- Một caller không được hủy computation đang phục vụ caller khác.

### Cache stampede sau eviction

Nếu một entry nóng bị eviction hoặc cache bị clear, nhiều request có thể đồng loạt miss. Single-flight, warmup có kiểm soát và eviction policy phù hợp giúp giảm spike.

### Reentrancy và dependency loading

Parser hoặc module loader có thể yêu cầu AST của dependency trong khi đang parse module cha. Cache manager cần hỗ trợ graph loading và phát hiện cycle mà không deadlock giữa các per-key lock.

## Thread safety và ownership của AST

AST cache thường là shared mutable infrastructure, trong khi AST được chia sẻ giữa nhiều request. Cần xác định ownership và thread-safety.

### Immutable tree

Sau khi publish, AST không được sửa. Nếu consumer cần annotation, dùng:
- Semantic side table riêng.
- Copy-on-write node.
- Immutable wrapper.
- Analysis result gắn với source version.

### Không lưu request state trong node

Không đặt current user, execution result hoặc mutable variable binding trực tiếp vào node dùng chung. Mỗi execution cần environment hoặc frame riêng.

### Safe publication

AST chỉ được đưa vào cache sau khi parse hoàn tất và mọi node đã được khởi tạo. Không publish một tree đang được parser tiếp tục sửa.

### Eviction khi đang dùng

Eviction khỏi cache không nhất thiết được phép giải phóng object ngay nếu request đang giữ reference. Runtime managed memory có thể giữ object đến khi không còn reference; native memory hoặc explicit resource cần reference counting hoặc lease.

### Memory visibility

Trong runtime đa luồng, cache map và entry metadata cần dùng synchronization hoặc concurrent data structure đúng cách. Không chỉ bảo vệ map mà bỏ qua trạng thái của entry, future hoặc dependency graph.

## Chiến lược eviction và giới hạn bộ nhớ

AST có thể lớn và tồn tại lâu. Cache cần có giới hạn để tránh tăng bộ nhớ không kiểm soát.

### LRU

Least Recently Used loại entry không được truy cập gần đây. LRU phù hợp khi truy cập gần đây là tín hiệu tốt cho khả năng sử dụng tiếp.

Hạn chế là một đợt scan nhiều module một lần có thể đẩy các entry nóng ra khỏi cache.

### LFU

Least Frequently Used ưu tiên giữ entry được truy cập nhiều. LFU có thể phù hợp với workload có tập module nóng ổn định, nhưng cần xử lý frequency aging để entry cũ không giữ vị trí quá lâu.

### TTL

Time To Live hết hạn entry sau một thời gian. TTL hữu ích cho cache có freshness requirement, nhưng AST của source immutable không nhất thiết cần hết hạn nếu content digest và version còn hợp lệ.

TTL không thay thế invalidation theo source change.

### Size-based eviction

Giới hạn theo tổng bytes hoặc weight thường tốt hơn chỉ giới hạn số entry, vì một AST nhỏ và một AST rất lớn có chi phí khác nhau.

Có thể đặt:
- Tổng cache budget.
- Maximum entry size.
- Maximum entries per workspace.
- Maximum source size.
- Maximum retained document versions.
- Budget riêng cho parsed AST và semantic metadata.

### Admission policy

Không phải mọi AST đều nên được cache. Có thể bỏ qua:
- Source rất nhỏ chỉ dùng một lần.
- Source vượt maximum entry size.
- Parse result lỗi không ổn định.
- Entry có hit probability thấp.
- Source trong chế độ ephemeral hoặc untrusted không được phép giữ lâu.

Admission policy cần dựa trên số liệu; quy tắc quá phức tạp có thể tốn nhiều hơn lợi ích.

### Cache partitioning

Có thể chia cache theo:
- Tenant.
- Workspace.
- Language version.
- Module namespace.
- Trust boundary.
- Runtime instance.

Partitioning giúp tránh một tenant hoặc project chiếm toàn bộ cache và giảm rủi ro chia sẻ entry qua boundary không phù hợp.

## Cache memory và garbage collection

AST thường gồm nhiều object nhỏ. Cấu trúc object-heavy có thể tạo overhead đáng kể so với kích thước source.

### Ước lượng footprint

Cần xem:
- Object header.
- Pointer/reference.
- Child list.
- String storage.
- Source buffer.
- Symbol text.
- Span metadata.
- Auxiliary indexes.
- Shared subtrees.

Một AST 1 MB source có thể chiếm nhiều MB heap tùy runtime và representation.

### Giữ source buffer

Nếu mỗi node giữ một substring riêng, memory có thể tăng do sao chép string. Nếu mọi node giữ reference đến một source buffer lớn, một subtree nhỏ có thể giữ cả file buffer sống lâu. Cần lựa chọn representation phù hợp.

### Weak reference

Weak reference cho phép garbage collector thu hồi AST khi không còn consumer mạnh, dù cache vẫn giữ weak entry. Điều này giảm áp lực giữ object nhưng khiến hit ratio khó dự đoán và có thể tạo parse lại thường xuyên.

Weak cache không thay thế size budget hoặc observability.

### Segmented cache

Có thể tách cache nóng và cache lạnh, hoặc chia theo workspace. Điều này tránh một nhóm request lớn làm eviction quá nhiều entry quan trọng của nhóm khác.

### GC pressure

Theo dõi heap used, allocation rate, pause time và cache retained size. Cache có thể giảm allocation ngắn hạn nhưng làm tăng live set và thời gian GC. Cần đo cả hai.

## Negative caching và cache lỗi parse

Trong editor, source có thể chưa hoàn chỉnh khi người dùng đang gõ. Parser có thể trả diagnostics và một recovery tree. Request tiếp theo có thể dùng lại kết quả đó nếu source chưa đổi.

### Negative cache

Negative cache lưu thông tin rằng một key đã parse thất bại hoặc không thể resolve. Nó tránh lặp lại công việc khi dependency vẫn chưa sẵn sàng.

### Điều kiện cache lỗi

Cần phân biệt:
- Syntax error phụ thuộc source content: có thể cache theo content digest.
- Module not found: phụ thuộc module search path và registry version.
- Permission denied: phụ thuộc principal và policy version.
- External service unavailable: không nên cache lâu như lỗi cú pháp.
- Cancellation: không phải parse failure và thường không nên cache như kết quả lỗi.

### Recovery AST

Parser có thể tạo AST một phần để editor vẫn hỗ trợ completion và diagnostics. Cache entry cần ghi trạng thái partial/recovered và diagnostics. Consumer thực thi DSL có thể yêu cầu AST không có syntax error, trong khi language server chấp nhận recovery tree.

### TTL và invalidation

Negative entry nên có TTL hoặc invalidation khi dependency/policy thay đổi. Nếu module not found được cache vô thời hạn, việc cài plugin hoặc thêm module mới sẽ không được nhận biết.

## Persisted AST cache và cache dùng chung giữa process

AST cache thường nằm trong memory của một process. Một số hệ thống muốn lưu cache trên disk hoặc chia sẻ giữa nhiều process để giảm startup cost.

### Disk cache

Disk cache có thể lưu serialized AST kèm:
- Cache key.
- Parser/grammar version.
- Schema của serialized format.
- Source digest.
- Dependency fingerprint.
- Checksum.
- Creation metadata.

Khi load, runtime cần xác minh metadata và checksum trước khi sử dụng.

### Serialization compatibility

AST object nội bộ có thể thay đổi giữa các phiên bản runtime. Serialized cache cần format version riêng và migration hoặc invalidation khi format không tương thích.

Không nên deserialize object tùy ý từ một cache location có thể bị người dùng khác ghi. Dữ liệu serialized có thể trở thành bề mặt tấn công nếu runtime loader không an toàn.

### Shared cache

Nhiều worker có thể dùng object store hoặc distributed cache chung. Cần cân nhắc:
- Network latency so với parse cost.
- Serialization/deserialization overhead.
- Cache stampede.
- Tenant isolation.
- Access control.
- Version namespace.
- Eviction và consistency.
- Availability khi cache service lỗi.

Distributed AST cache chỉ có lợi khi parse đủ đắt và reuse đủ cao. Với AST nhỏ, local memory cache có thể nhanh và đơn giản hơn.

### Cache fallback

Nếu disk hoặc distributed cache không khả dụng, hệ thống thường có thể parse lại từ source. Cache là optimization, không nên là nguồn dữ liệu duy nhất để phục hồi DSL definition.

### Content-addressed cache

Một cache theo content digest có thể chia sẻ artifact giữa các worker nếu parser version và options tương thích. Đây là cách hữu ích trong build system, nhưng cache key cần bao gồm toàn bộ dependency và toolchain fingerprint.

## Security và trust boundary

AST có thể chứa source text, identifier, literal và metadata nhạy cảm. Cache cần tuân thủ cùng policy bảo mật như source.

### Không chia sẻ cross-tenant ngoài ý muốn

Nếu AST chỉ phụ thuộc source công khai và parser config, có thể chia sẻ immutable artifact giữa tenant theo policy. Nhưng nếu AST chứa source location, resolved path, macro expansion hoặc metadata có thể tiết lộ cấu trúc nội bộ, cần partition theo security boundary.

### Cache poisoning

Cache poisoning xảy ra khi attacker ghi entry giả hoặc làm hệ thống nhận nhầm entry của source khác. Giảm rủi ro bằng:
- Content digest.
- Authenticated cache namespace.
- Checksum hoặc signature cho persisted artifact.
- Kiểm tra parser/grammar version.
- Không tin key do client tự cung cấp.
- Kiểm tra source identity và digest cùng nhau.

### Path traversal và source identity

Nếu cache file được đặt theo module path, cần canonicalize path và tránh dùng raw input để tạo file location. Module ID phải được resolve trong workspace hoặc namespace được phép.

### Sensitive source

AST có thể chứa literal như token, connection string hoặc query nhạy cảm. Không ghi toàn bộ AST vào log hoặc telemetry. Persistent cache cần access control, encryption-at-rest khi phù hợp và retention policy.

### Plugin và grammar extension

Extension có thể thêm node type hoặc parser hook. Cache entry được tạo với extension version cũ không nên được load khi registry mới không tương thích. Plugin code và metadata cần được xác thực theo trust policy.

## AST cache trong host application

Host application thường có nhiều nơi sử dụng DSL: request handler, scheduler, background worker, API, plugin và admin tool.

### Cache ownership

Cần quyết định cache thuộc:
- Một DSL runtime instance.
- Một application process.
- Một workspace.
- Một tenant.
- Một module registry.
- Một shared service.

Cache quá cục bộ có thể tạo duplicate memory; cache quá toàn cục có thể làm phức tạp security và invalidation.

### Dependency injection

Host có thể cung cấp AST cache qua interface:

~~~text
AstCache
  get(key)
  put(key, ast, metadata)
  invalidate(sourceId)
  invalidateNamespace(namespace)
  stats()
~~~

Parser và module loader dùng interface thay vì phụ thuộc trực tiếp vào implementation LRU hoặc distributed cache. Test có thể dùng in-memory fake cache để kiểm tra behavior.

### Lifecycle

Cache cần được tạo trước khi runtime nhận request và đóng đúng cách khi host shutdown. Nếu dùng disk cache, cần flush metadata hoặc đóng file handle. Nếu cache chỉ là memory, cần tránh giữ reference từ static registry sau khi host context đã đóng.

### Multiple runtime versions

Một host có thể chạy nhiều DSL version hoặc plugin set. Cache namespace cần phân biệt runtime configuration để AST của grammar này không bị dùng trong runtime khác.

### Warmup

Host có thể preload module thường dùng khi startup. Warmup nên có concurrency limit và timeout để không làm ứng dụng khởi động quá lâu. Có thể ưu tiên module thiết yếu rồi tải lazy các module còn lại.

## AST cache trong IDE và Language Server

Language server nhận nhiều document change và request như completion, hover, diagnostics, definition hoặc references. Một AST cache tốt có thể giảm parse lặp lại giữa các request.

### Chia sẻ AST giữa các LSP request

Một document snapshot có thể được dùng bởi:
- Diagnostics.
- Completion.
- Hover.
- Go to definition.
- Document symbols.
- Formatting hoặc code action.

Các request cần dùng cùng document version nếu muốn kết quả nhất quán. Nếu một request cũ đến sau khi document đã đổi, server cần xác định có thể phục vụ version cũ hay phải hủy.

### Document lifecycle

- didOpen: tạo document snapshot và có thể parse ngay.
- didChange: áp dụng edit, cập nhật version và invalidation.
- didSave: có thể đồng bộ source với disk.
- didClose: giải phóng cache riêng của document nếu không còn consumer.
- Workspace change: invalidation module dependency hoặc index.

### Cancellation

Một request completion có thể bị hủy khi người dùng tiếp tục gõ. Nếu parse đang chạy cho nhiều request cùng key, cancellation của một caller không nên hủy computation chung khi caller khác vẫn cần. Có thể dùng reference count hoặc cancellation scope cho từng waiter.

### Diagnostics theo version

Diagnostics phải gắn với document version. Cache không được trả diagnostics cũ sau khi source đã thay đổi. Recovery AST có thể được tái dùng cho nhiều tính năng editor nhưng phải được đánh dấu là partial.

### Incremental parse metrics

Có thể theo dõi:
- Incremental parse hit.
- Full parse fallback.
- Reused subtree count.
- Parse duration theo document size.
- AST cache hit ratio.
- Version mismatch.
- Stale request cancellation.
- Memory theo workspace.

Không đưa source text hoặc path riêng tư vào metric labels.

## Cache invalidation trong môi trường nhiều process và nhiều node

Nếu nhiều host instance cùng nạp một module, một thay đổi source cần được nhận biết nhất quán.

### Versioned source registry

Một source registry có thể phát version hoặc content digest. Mỗi process so sánh local cache với version hiện tại. Event invalidation có thể giảm độ trễ nhưng không nên là nguồn xác thực duy nhất nếu message có thể bị mất.

### Pub/sub invalidation

Một process cập nhật module có thể publish event invalidation. Các process khác xóa hoặc đánh dấu entry stale. Event cần có module ID, new digest và namespace.

### Pull-based validation

Trước khi dùng entry, process có thể kiểm tra source version qua registry hoặc manifest. Cách này đáng tin hơn nhưng có chi phí lookup. Có thể cache version metadata với TTL ngắn.

### Race giữa update và invalidation

Một process có thể nhận invalidation cũ sau khi đã nạp version mới. Invalidation cần mang version hoặc digest để không xóa nhầm entry mới hơn.

### Eventual invalidation

Trong hệ thống phân tán, có thể tồn tại một khoảng thời gian process A dùng AST version mới trong khi process B chưa nhận invalidation. Nếu tính nhất quán là bắt buộc, cần version pinning trong execution request hoặc kiểm tra version trước action quan trọng.

### Cache namespace và deployment rollout

Khi rollout parser version mới, không nên trộn AST serialized của runtime cũ và mới. Có thể namespace theo parser build ID hoặc grammar fingerprint và dọn namespace cũ sau khi rollout hoàn tất.

## Đo lường và observability cho AST cache

Không thể biết cache có hữu ích chỉ bằng việc thấy số entry tăng. Cần đo hit, miss, latency, size và invalidation.

Các metrics cơ bản:

~~~text
dsl_ast_cache_requests_total
dsl_ast_cache_hits_total
dsl_ast_cache_misses_total
dsl_ast_cache_evictions_total
dsl_ast_cache_invalidations_total
dsl_ast_cache_entries
dsl_ast_cache_memory_bytes
dsl_ast_parse_duration_seconds
dsl_ast_cache_lookup_duration_seconds
dsl_ast_cache_load_errors_total
~~~

### Hit ratio

Hit ratio có thể tính:

~~~text
hit ratio = cache hits / (cache hits + cache misses)
~~~

Cần định nghĩa request nào được tính là lookup và xử lý bypass. Hit ratio cao không luôn đồng nghĩa hiệu năng tốt nếu lookup đắt hoặc cache giữ quá nhiều memory.

### Parse latency

Đo parse duration theo source size bucket và grammar version. So sánh cache hit path với parse path để biết lợi ích thực tế.

### Eviction và churn

Eviction rate cao có thể cho thấy cache quá nhỏ, workload quá rộng hoặc admission policy chưa phù hợp. Nếu entry vừa được parse đã bị eviction trước lần dùng tiếp theo, cache không mang lại nhiều lợi ích.

### Invalidation metrics

Đo số entry bị invalidation theo nguyên nhân:
- Source changed.
- Grammar version changed.
- Dependency changed.
- Plugin registry changed.
- Manual clear.
- TTL expired.

Invalidation quá rộng có thể tạo parse storm. Cần phân biệt targeted invalidation với clear namespace.

### Memory và GC

Theo dõi retained bytes, heap pressure, allocation rate và GC pause. Cache nên có dashboard và alert khi memory vượt budget hoặc eviction liên tục tăng.

### Trace

Một trace cho module load có thể chứa:
- Cache key fingerprint đã rút gọn.
- Hit/miss.
- Parse duration.
- Dependency resolution.
- AST node count.
- Cache admission result.

Không ghi raw source hoặc secret literal vào span attribute.

## Kiểm thử AST cache

AST cache cần được kiểm thử về correctness, invalidation, concurrency, memory behavior và compatibility.

### Cache hit

Gọi loader hai lần với cùng source và parser config. Xác nhận lần thứ hai dùng entry cũ và parser không bị gọi lại nếu cache contract yêu cầu.

### Cache miss

Thay đổi content digest hoặc parser options. Xác nhận key khác và parser tạo AST mới.

### Source invalidation

Nạp version 1, thay source thành version 2 rồi yêu cầu AST. Xác nhận request mới không nhận tree version 1.

### Grammar version

Dùng cùng source với hai grammar version khác nhau. Xác nhận cache không chia sẻ entry nếu AST semantics có thể khác.

### Dependency invalidation

Nạp module có include hoặc macro dependency, thay dependency và xác nhận đúng artifact bị invalidation. Nếu chỉ semantic model phụ thuộc, AST gốc có thể vẫn được giữ; test cần xác nhận cache layer phù hợp.

### Parse failure và negative cache

Gửi source không hợp lệ, sau đó sửa source. Xác nhận diagnostics cũ không còn áp dụng và entry lỗi được invalidation theo digest mới.

### Concurrent miss

Gửi nhiều request đồng thời cùng một key. Nếu dùng single-flight, xác nhận chỉ một parse computation được thực hiện và tất cả caller nhận kết quả hợp lệ.

### Cancellation

Hủy một waiter trong khi parse chung vẫn được caller khác dùng. Xác nhận cancellation không làm hỏng shared computation hoặc cache entry.

### Eviction

Tạo nhiều AST vượt budget. Xác nhận eviction giữ memory trong giới hạn và không làm hỏng request đang dùng reference đến entry bị evict.

### Thread safety

Chạy lookup, invalidation và parse đồng thời. Xác nhận không có entry nửa khởi tạo, stale publish hoặc race làm trả AST sai version.

### Persistence compatibility

Nếu có disk cache, kiểm tra:
- Checksum sai.
- Format version cũ.
- Parser version không tương thích.
- File cache bị truncate.
- Permission denied.
- Cache path không hợp lệ.

Trong các trường hợp này, hệ thống nên bỏ entry không hợp lệ và parse lại từ source nếu có thể.

### Security test

Xác nhận cache namespace không cho tenant khác đọc entry nhạy cảm, source secret không xuất hiện trong logs và persisted cache không được load từ path không tin cậy.

### Performance test

Đo:
- Cold parse.
- Warm cache hit.
- Cache lookup overhead.
- Memory footprint.
- Hit ratio trên workload đại diện.
- Concurrent miss.
- Invalidation burst.
- Incremental parse so với full parse.

Benchmark nên dùng source có kích thước và cấu trúc đa dạng, không chỉ một file nhỏ.

## Các lỗi thiết kế thường gặp

### Chỉ dùng file path làm cache key

Nội dung file có thể thay đổi trong khi path giữ nguyên. Cần content digest hoặc source version đáng tin cậy.

### Bỏ qua grammar và parser options

Cùng source có thể tạo AST khác theo language version hoặc feature flag. Cache key phải nhận diện cấu hình parse.

### Đưa runtime state vào AST

AST dùng chung có thể làm rò rỉ user, tenant hoặc result giữa request. Giữ runtime state trong execution context riêng.

### Sửa AST sau khi đưa vào cache

Mutable tree dễ tạo race và kết quả phụ thuộc thứ tự request. Dùng immutable AST hoặc copy-on-write.

### Không invalidation dependency

Module cha có thể tiếp tục dùng AST đã expand từ include cũ. Theo dõi dependency fingerprint và invalidation phù hợp từng artifact.

### Clear toàn bộ cache cho mọi thay đổi

Clear-all tạo parse spike và làm giảm hit ratio. Invalidate theo source, dependency hoặc namespace cụ thể.

### Cache lỗi vô thời hạn

Negative cache có thể giữ lỗi module not found hoặc permission denied sau khi dependency/policy đã thay đổi. Gắn error entry với version và TTL phù hợp.

### Không giới hạn memory

Giữ AST của mọi file có thể làm tăng heap và GC pause. Dùng size budget, eviction và partitioning.

### Single-flight cancellation sai

Một caller hủy request có thể vô tình hủy parse đang phục vụ nhiều caller. Tách cancellation của waiter khỏi lifetime của shared computation.

### Tái sử dụng serialized AST không tương thích

AST format có thể thay đổi giữa runtime version. Gắn format version, parser fingerprint và checksum.

### Chỉ nhìn hit ratio

Hit ratio cao có thể đi kèm memory quá lớn hoặc parse vẫn là phần nhỏ của latency tổng. Theo dõi parse time, lookup cost, memory và end-to-end latency.

### Dùng cache như nguồn dữ liệu chính

Cache có thể bị mất hoặc hỏng. Source DSL và module registry mới là nguồn dữ liệu có thẩm quyền; cache cần có thể tái tạo.

## Quy trình triển khai AST cache cho DSL

Một quy trình thực tế có thể đi theo các bước:

1. **Đo baseline:** xác định parse frequency, parse duration, source size và phần latency do parsing.
2. **Xác định cache boundary:** quyết định lưu token stream, AST, recovery AST hay nhiều lớp riêng.
3. **Định nghĩa AST ownership:** chọn immutable tree, source snapshot và cách giữ source metadata.
4. **Thiết kế cache key:** bao gồm source identity/content digest, grammar version, parser options và dependency fingerprint cần thiết.
5. **Xây cache entry:** lưu AST, version, diagnostics, dependency và size metadata.
6. **Triển khai lookup/miss:** parse khi miss và publish entry chỉ sau khi parse hoàn tất.
7. **Thiết kế invalidation:** source change, dependency, grammar, plugin và manual invalidation.
8. **Hỗ trợ concurrency:** single-flight, safe publication, cancellation và thread-safe eviction.
9. **Đặt memory budget:** size-based eviction, admission, partitioning và giới hạn document version.
10. **Xử lý incremental parsing:** reuse subtree, version history và full parse fallback nếu DSL/editor cần.
11. **Quyết định persistence:** chỉ thêm disk hoặc shared cache khi benchmark chứng minh có lợi.
12. **Bảo vệ security:** tenant namespace, cache poisoning defense, path validation và sensitive data handling.
13. **Thêm observability:** hit/miss, parse latency, invalidation, eviction, memory và GC.
14. **Kiểm thử:** correctness, versioning, dependency, concurrency, cancellation, eviction, compatibility và security.
15. **Đánh giá bằng workload thật:** so sánh cold/warm execution, memory và tail latency trước khi rollout.

Mỗi cache layer nên có một contract rõ: artifact được lưu, các input tạo nên key, điều kiện invalidation, thời gian sống, giới hạn memory, ownership và behavior khi cache unavailable. Contract này giúp host application, compiler, language server và runtime dùng cache nhất quán.

## Kết luận

Bộ nhớ đệm AST giúp DSL tái sử dụng cấu trúc cú pháp đã parse thay vì lặp lại lexing và parsing cho cùng một source. Nó có thể giảm CPU, allocation, startup cost và latency khi module được sử dụng nhiều lần. Hiệu quả phụ thuộc vào workload, cache hit ratio và chi phí quản lý entry.

Một implementation đáng tin cậy cần cache key bao phủ source content, grammar version và parser options; tách AST khỏi semantic và runtime state; dùng immutable tree; theo dõi dependency; invalidation đúng khi source hoặc grammar thay đổi; và xử lý concurrent miss bằng cơ chế như single-flight. Memory budget, eviction, incremental parsing, persistence và tenant isolation cần được thiết kế theo môi trường sử dụng.

AST cache phải là một optimization có thể tái tạo từ source chính thức. Khi cache entry lỗi, hết hạn hoặc không tương thích, hệ thống có thể loại bỏ và parse lại. Metrics, tracing và kiểm thử về invalidation, concurrency, memory, cancellation và security giúp xác nhận cache thực sự cải thiện hiệu năng mà không làm sai kết quả hoặc rò rỉ dữ liệu.
