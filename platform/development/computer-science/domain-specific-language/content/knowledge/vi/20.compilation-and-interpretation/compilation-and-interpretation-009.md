# Bộ nhớ đệm kết quả

Trong quá trình biên dịch và thông dịch một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), nhiều phép tính có thể được thực hiện lặp lại với cùng đầu vào. Compiler có thể phải phân tích lại một module không thay đổi; bộ kiểm tra kiểu có thể suy luận lại kiểu của cùng một biểu thức; interpreter có thể đánh giá nhiều lần một biểu thức thuần; hệ thống quy tắc có thể tính lại một quyết định từ cùng dữ liệu và cùng chính sách. Nếu kết quả trước đó vẫn còn hợp lệ, hệ thống có thể lưu và dùng lại thay vì thực hiện lại toàn bộ công việc.

**Bộ nhớ đệm kết quả** (*result caching*) là kỹ thuật lưu kết quả của một phép xử lý cùng với thông tin đủ để xác định khi nào có thể sử dụng lại kết quả đó. Khi một yêu cầu mới có cùng đầu vào hiệu lực và các phụ thuộc liên quan chưa thay đổi, hệ thống lấy kết quả từ cache. Khi đầu vào hoặc một phụ thuộc thay đổi, kết quả cũ phải được bỏ qua, làm mới hoặc tính lại.

Ví dụ, một DSL mô tả chính sách phê duyệt đơn hàng có thể tính:

~~~text
decision = evaluate OrderApproval(order, policyVersion = "v4");
~~~

Nếu `evaluate` chỉ phụ thuộc vào nội dung đơn hàng, phiên bản chính sách `v4`, cấu hình và các dữ liệu đã được cố định, hệ thống có thể lưu quyết định cho một khóa đầu vào xác định. Lần sau, khi cùng đơn hàng và cùng các phụ thuộc được đánh giá, cache có thể trả lại quyết định đã lưu. Nhưng nếu trạng thái khách hàng, quyền người dùng hoặc bảng rủi ro đã thay đổi mà không được đưa vào khóa cache hoặc cơ chế invalidation, kết quả cũ có thể trở nên sai.

Do đó, result caching không đơn giản là lưu một giá trị vào map. Thiết kế phải xác định chính xác kết quả nào được cache, đầu vào nào quyết định kết quả, phụ thuộc nào có thể làm kết quả mất hiệu lực, thời gian lưu giữ, phạm vi chia sẻ và cách xử lý khi nhiều yêu cầu cùng truy cập. Cache chỉ an toàn khi hệ thống có thể chứng minh rằng kết quả được tái sử dụng vẫn tương đương với kết quả tính mới theo ngữ nghĩa DSL.

## 1. Bộ nhớ đệm kết quả là gì?

Một cache là vùng lưu trữ kết quả đã tính trước để phục vụ yêu cầu sau. Cache thường được tổ chức dưới dạng ánh xạ từ khóa (*cache key*) sang giá trị (*cached value*):

~~~text
cache[key] = result
~~~

Khi có yêu cầu:

1. Hệ thống xác định đầu vào hiệu lực của phép xử lý.
2. Tạo cache key từ đầu vào và các phụ thuộc cần thiết.
3. Tìm key trong cache.
4. Nếu tìm thấy kết quả còn hợp lệ, trả kết quả đã lưu (*cache hit*).
5. Nếu không tìm thấy hoặc kết quả hết hiệu lực, tính lại (*cache miss*), lưu kết quả mới rồi trả về.

### Cache hit và cache miss

- **Cache hit:** khóa được tìm thấy và kết quả thỏa điều kiện sử dụng lại.
- **Cache miss:** không có kết quả phù hợp, kết quả đã hết hạn hoặc không thể xác minh tính hợp lệ.
- **Cache invalidation:** đánh dấu hoặc loại bỏ kết quả không còn đáng tin cậy do phụ thuộc thay đổi.
- **Cache eviction:** loại bỏ một mục để giải phóng dung lượng, thường theo chính sách LRU, LFU hoặc giới hạn bộ nhớ.

Cache hit chỉ là một sự kiện tra cứu thành công; nó không tự chứng minh kết quả đúng. Tính đúng đắn đến từ thiết kế khóa, dependency tracking và quy tắc invalidation.

### Ví dụ đơn giản

Giả sử compiler tính bảng symbol của một module từ nội dung nguồn:

~~~text
symbolTable = buildSymbolTable(moduleSource);
~~~

Nếu nội dung nguồn và các tùy chọn ảnh hưởng đến cách thu thập khai báo không đổi, có thể dùng lại symbol table. Nếu module thay đổi khai báo public, module phụ thuộc có thể cần được phân tích lại dù nội dung của chúng không đổi.

## 2. Vì sao compiler và interpreter cần cache?

### Tránh tính toán lặp lại

Một biểu thức thuần có thể được đánh giá nhiều lần với cùng đối số. Một module không đổi có thể được build trong nhiều lần chạy. Một grammar hoặc schema có thể được tải lại trong nhiều phiên thực thi. Cache giúp tránh lặp lại những công việc có kết quả ổn định.

### Tăng tốc biên dịch gia tăng

Trong dự án DSL gồm nhiều module, một thay đổi nhỏ thường chỉ ảnh hưởng đến một phần dependency graph. Nếu các module khác không thay đổi và phụ thuộc của chúng vẫn hợp lệ, compiler có thể tái sử dụng artifact hoặc kết quả phân tích trước đó.

### Giảm độ trễ khi chạy

Interpreter có thể cache kết quả của biểu thức, truy vấn hoặc quy tắc được gọi thường xuyên. Hệ thống workflow có thể cache metadata của policy đã compile. Các lần gọi sau có thể bỏ qua bước khởi tạo hoặc tính toán tốn kém.

### Giảm tải cho tài nguyên bên ngoài

Một số DSL đọc schema, catalog, bảng cấu hình hoặc metadata từ dịch vụ. Cache có thể giảm số lần truy vấn và cải thiện khả năng hoạt động khi dịch vụ chậm. Tuy nhiên, cache không được che giấu thay đổi dữ liệu nếu nghiệp vụ yêu cầu đọc giá trị mới nhất.

### Tăng khả năng tái lập

Cache theo nội dung và phiên bản có thể giúp nhận diện artifact nào được tạo từ đầu vào nào. Khi build có tính tái lập, hệ thống có thể chia sẻ artifact giữa máy phát triển, CI và môi trường build khác.

## 3. Phân biệt các loại cache trong pipeline DSL

Từ “result cache” có thể chỉ nhiều tầng khác nhau. Cần phân biệt chúng vì đầu vào, giá trị lưu và quy tắc invalidation không giống nhau.

| Loại cache | Kết quả được lưu | Ví dụ |
|---|---|---|
| Source/read cache | Nội dung nguồn đã đọc hoặc giải mã | Buffer UTF-8 đã giải mã thành `SourceText`. |
| Lexical cache | Token và lexical state | Token stream của module không đổi. |
| Parse cache | CST/AST hoặc parse fragment | Cây cú pháp của một file theo grammar version. |
| Semantic cache | Symbol table, kiểu, kết quả phân giải | Kiểu đã suy luận của biểu thức thuần. |
| Compilation cache | IR hoặc artifact đã biên dịch | Bytecode hoặc mã đích của module. |
| Query/result cache | Kết quả truy vấn hoặc đánh giá quy tắc | Danh sách đối tượng thỏa điều kiện. |
| Runtime memoization | Kết quả lời gọi hàm thuần | `calculateTax(rate, amount)`. |
| Metadata cache | Thông tin phụ trợ | Module graph, schema đã tải hoặc capability metadata. |

Các tầng có thể phụ thuộc nhau. Nếu lexer tạo token mới, parse cache tương ứng có thể mất hiệu lực; nếu AST không đổi nhưng một thư viện kiểu hoặc cấu hình semantic thay đổi, semantic cache có thể phải tính lại; nếu IR không đổi nhưng compiler backend version thay đổi, compilation cache có thể không còn dùng được.

### Cache artifact và cache kết quả thực thi

**Artifact cache** lưu sản phẩm của quá trình biên dịch như AST, IR, bytecode hoặc mã đích. Kết quả thường phụ thuộc nội dung nguồn, compiler, tùy chọn build và dependency.

**Execution result cache** lưu giá trị được tạo khi chạy chương trình. Kết quả có thể phụ thuộc dữ liệu nghiệp vụ, trạng thái hệ thống, người dùng, thời gian và các dịch vụ ngoài. Cache kết quả thực thi thường có yêu cầu invalidation và bảo mật nghiêm ngặt hơn.

Không nên dùng chung một quy tắc cache key cho hai loại. Cùng source code không có nghĩa hai lần chạy có cùng dữ liệu hoặc cùng quyền.

## 4. Vị trí cache trong pipeline biên dịch và thông dịch

Một pipeline DSL điển hình có thể gồm:

~~~mermaid
flowchart TD
    A[Source files] --> B[Source cache]
    B --> C[Lexer]
    C --> D[Token cache]
    D --> E[Parser]
    E --> F[AST / Parse cache]
    F --> G[Name and type analysis]
    G --> H[Semantic cache]
    H --> I[Lowering]
    I --> J[IR cache]
    J --> K[Code generation]
    K --> L[Artifact cache]
    L --> M[Interpreter or runtime]
    M --> N[Execution result cache]
~~~

Không phải hệ thống nào cũng cần cache ở mọi tầng. Một compiler nhỏ có thể chỉ cache artifact cuối. IDE có thể cần token và parse cache để phản hồi nhanh. Interpreter phục vụ nhiều request có thể cần cache compiled expression và memoization cho các hàm thuần.

### Cache theo tầng

Một tầng nên cache khi:

- Công việc đủ tốn kém hoặc được gọi đủ thường xuyên.
- Kết quả có thể được định danh bằng khóa ổn định.
- Hệ thống biết các phụ thuộc làm kết quả thay đổi.
- Chi phí lưu và kiểm tra cache nhỏ hơn chi phí tính lại trong workload mục tiêu.

Cache không mặc nhiên làm chương trình nhanh hơn. Với phép tính rẻ hoặc kết quả ít được dùng lại, chi phí tạo key, tra cứu, đồng bộ và cấp phát có thể lớn hơn tính lại.

## 5. Cache key – khóa xác định kết quả

Cache key là thành phần quan trọng nhất của một thiết kế cache đúng. Hai yêu cầu chỉ được dùng chung một kết quả khi chúng tương đương theo mọi đầu vào có thể ảnh hưởng kết quả.

### Khóa quá ngắn gây lỗi gì?

Giả sử kết quả compile chỉ được cache theo tên file:

~~~text
key = "policies/order.dsl"
~~~

Nếu nội dung file thay đổi nhưng tên không đổi, cache có thể trả artifact cũ. Nếu cùng tên file tồn tại ở hai workspace, artifact của workspace này có thể bị dùng nhầm cho workspace khác.

### Khóa cần bao gồm các phụ thuộc hiệu lực

Một compilation key có thể gồm:

- Hash nội dung nguồn hoặc hash của AST đầu vào.
- Phiên bản compiler và frontend.
- Phiên bản grammar hoặc language specification.
- Các cờ và tùy chọn biên dịch.
- Phiên bản thư viện, module phụ thuộc và schema.
- Target platform, ABI hoặc backend configuration.
- Các biến môi trường được phép ảnh hưởng kết quả.
- Phiên bản plugin hoặc extension có tham gia compiler.

Một runtime result key có thể gồm:

- Định danh hàm, rule hoặc biểu thức.
- Các đối số sau chuẩn hóa.
- Snapshot hoặc version của dữ liệu phụ thuộc.
- Context nghiệp vụ cần thiết.
- Tenant, principal hoặc security scope nếu kết quả phụ thuộc quyền.
- Clock, timezone, locale hoặc random seed nếu có ảnh hưởng.

Danh sách cụ thể phụ thuộc hợp đồng của phép xử lý. Không cần đưa dữ liệu không ảnh hưởng kết quả vào key, nhưng không được bỏ sót một phụ thuộc có ảnh hưởng.

### Hash nội dung

Một cách phổ biến là tạo hash từ các thành phần đã chuẩn hóa:

~~~text
cacheKey = hash(
    sourceContent,
    compilerVersion,
    grammarVersion,
    compileOptions,
    dependencyFingerprints
)
~~~

Hash giúp key gọn và hỗ trợ content-addressable storage. Tuy nhiên, hash không thay thế việc xác định đúng thành phần đầu vào. Nếu dependency fingerprint thiếu, key vẫn có thể đại diện sai cho kết quả. Hệ thống cũng cần chọn thuật toán hash phù hợp với yêu cầu chống va chạm và mức độ tin cậy.

### Chuẩn hóa đầu vào

Nếu hai biểu thức có cùng ý nghĩa nhưng khác cách viết, có thể cân nhắc tạo key từ AST chuẩn hóa thay vì văn bản nguồn. Ví dụ `a + b` và `a+b` có thể tạo cùng AST. Tuy nhiên, nếu comment, vị trí nguồn hoặc định dạng được giữ trong artifact, source text vẫn có thể là một phụ thuộc cần đưa vào key.

Chuẩn hóa phải bảo toàn ngữ nghĩa. Không được sắp xếp toán hạng hoặc loại bỏ cấu trúc chỉ vì chúng trông tương đương nếu DSL cho phép tác dụng phụ hoặc có quy tắc đánh giá thứ tự.

## 6. Fingerprint và content-addressable cache

Fingerprint là dấu vân tay đại diện cho nội dung hoặc trạng thái phụ thuộc. Một cache có thể dùng fingerprint để xác định hai đầu vào có tương đương hay không.

### Fingerprint của module

Một module có thể có fingerprint được tính từ:

~~~text
moduleFingerprint = hash(
    normalizedSource,
    publicInterfaceFingerprint,
    compilerFrontendVersion,
    relevantOptions
)
~~~

Nếu module chỉ thay đổi phần triển khai nội bộ và public interface không đổi, một số module phụ thuộc có thể không cần biên dịch lại. Nhưng điều này chỉ an toàn nếu artifact phụ thuộc chỉ cần public interface và không inline hoặc đọc nội dung triển khai của module đó.

### Merkle tree

Với dự án có nhiều module, có thể xây dựng Merkle tree: fingerprint của node cha được tính từ fingerprint của chính nó và các node con phụ thuộc.

~~~mermaid
flowchart TD
    A[Project fingerprint]
    A --> B[Module A fingerprint]
    A --> C[Module B fingerprint]
    A --> D[Module C fingerprint]
    B --> E[Source A + dependencies]
    C --> F[Source B + dependencies]
    D --> G[Source C + dependencies]
~~~

Khi một module thay đổi, fingerprint của các node phụ thuộc có thể được tính lại. Những nhánh không bị ảnh hưởng có thể giữ nguyên. Cách này hữu ích cho build cache và hệ thống phân phối artifact.

### Content-addressable storage

Trong content-addressable cache, artifact được lưu theo hash của đầu vào hoặc nội dung artifact thay vì tên tùy ý. Nhiều workspace có cùng đầu vào hiệu lực có thể dùng chung artifact. Cần phân vùng quyền truy cập và xác thực metadata để không dùng nhầm artifact giữa các dự án hoặc tenant.

## 7. Dependency tracking – theo dõi phụ thuộc

Cache key chỉ có thể đầy đủ nếu hệ thống biết kết quả phụ thuộc vào những gì. **Dependency tracking** ghi nhận các dữ liệu, khai báo, module, cấu hình hoặc tài nguyên mà phép xử lý đã đọc.

Ví dụ, khi compile module `OrderPolicy`, compiler có thể ghi nhận nó phụ thuộc vào:

- Kiểu `Order` trong `OrderModel`.
- Kiểu `Customer` trong `CustomerModel`.
- Hành động `ApproveOrder` trong `ApprovalActions`.
- Schema của `Payment`.
- Phiên bản grammar và compiler frontend.

Nếu một phụ thuộc thay đổi, cache của `OrderPolicy` có thể cần được invalidated.

### Dependency graph

~~~mermaid
flowchart LR
    A[OrderPolicy] --> B[OrderModel]
    A --> C[CustomerModel]
    A --> D[ApprovalActions]
    A --> E[PaymentSchema]
~~~

Mũi tên biểu diễn `OrderPolicy` phụ thuộc vào node đích. Khi `CustomerModel` thay đổi, hệ thống truy ngược các node phụ thuộc để xác định kết quả nào cần tính lại.

### Phụ thuộc trực tiếp và gián tiếp

Module A có thể tham chiếu B, còn B tham chiếu C. A không trực tiếp đọc C nhưng kết quả compile của A có thể phụ thuộc vào C thông qua giao diện hoặc ngữ nghĩa của B. Dependency tracking cần tính đến transitive dependency khi hợp đồng module yêu cầu.

### Ghi nhận phụ thuộc khi tính kết quả

Một cách triển khai là tạo dependency collector trong context của compiler hoặc interpreter:

~~~text
evaluate(expression, context):
    result = compute(expression)
    dependencies = context.readDependencies()
    cache.put(key(expression, dependencies), result)
    return result
~~~

Mỗi lần đọc symbol, schema hoặc dữ liệu ngoài, thành phần tương ứng ghi nhận fingerprint hoặc version đã dùng. Khi tra cache, hệ thống kiểm tra các version đó còn phù hợp.

### Phụ thuộc động

Một biểu thức có thể chỉ đọc một nhánh tùy theo điều kiện. Ví dụ:

~~~text
if customer.isBusiness then businessRate else personalRate
~~~

Nếu chỉ nhánh `businessRate` được đọc, kết quả thực tế có thể không phụ thuộc `personalRate` trong lần đánh giá đó. Cache có thể lưu dependency động theo các giá trị đã đọc. Tuy nhiên, cách này cần bảo đảm điều kiện chọn nhánh và mọi phụ thuộc điều khiển cũng được ghi nhận. Một lựa chọn đơn giản hơn là ghi nhận tất cả dependency tĩnh có thể ảnh hưởng biểu thức, chấp nhận invalidation rộng hơn.

## 8. Cache invalidation – khi nào phải bỏ kết quả cũ?

Cache invalidation là việc đánh dấu kết quả không còn dùng được sau khi một đầu vào hoặc phụ thuộc thay đổi. Đây thường là phần khó nhất của thiết kế cache.

### Invalidation theo version

Mỗi module, schema hoặc policy có version tăng dần. Cache entry ghi lại version đã dùng. Khi version hiện tại khác version trong entry, kết quả không còn hợp lệ.

~~~text
entry.dependencies = {
    OrderModel: 12,
    CustomerModel: 7
}

current.dependencies = {
    OrderModel: 12,
    CustomerModel: 8
}
~~~

Do `CustomerModel` đã chuyển từ version 7 sang 8, entry phải được tính lại nếu kết quả phụ thuộc vào phiên bản đó.

### Invalidation theo dependency graph

Khi một node thay đổi, hệ thống đánh dấu các node phụ thuộc trực tiếp và gián tiếp là dirty. Cách này phù hợp với compiler gia tăng, nơi dependency graph đã được xây dựng trong quá trình phân tích.

### Invalidation theo TTL

TTL (*time to live*) quy định thời gian một cache entry được xem là còn mới. Sau TTL, entry bị xem là hết hạn hoặc cần xác thực lại.

TTL hữu ích khi phụ thuộc là dữ liệu ngoài không có notification hoặc version rõ ràng. Tuy nhiên, TTL chỉ giới hạn độ cũ; nó không bảo đảm tính đúng đắn tức thời. Nếu dữ liệu thay đổi ngay sau khi cache được ghi, kết quả vẫn có thể cũ trong khoảng TTL còn lại.

### Invalidation chủ động

Khi một thao tác cập nhật dữ liệu thành công, hệ thống có thể phát sự kiện invalidation cho các cache phụ thuộc. Ví dụ, khi bảng giá được publish phiên bản mới, cache kết quả tính giá liên quan được đánh dấu hết hiệu lực.

### Invalidation theo namespace

Có thể phân vùng cache theo project, tenant, environment hoặc compiler version. Khi một phạm vi được thay đổi, hệ thống loại bỏ hoặc chuyển sang namespace mới. Cách này đơn giản hóa invalidation nhưng có thể làm mất nhiều cache entry hơn mức cần thiết.

### Cache busting

Cache busting tạo key mới khi một thành phần quan trọng thay đổi, ví dụ tăng `compilerVersion` hoặc `schemaEpoch`. Các entry cũ có thể được giữ cho đến khi eviction thay vì xóa ngay. Cách này giảm nguy cơ dùng nhầm entry nếu key mới được tạo chính xác.

## 9. Chiến lược invalidation theo từng loại cache

Không nên dùng một chính sách cho mọi tầng.

| Cache | Thay đổi làm mất hiệu lực | Cơ chế thường dùng |
|---|---|---|
| Token cache | Source text, encoding hoặc lexer configuration | Source version/hash và edit range. |
| Parse cache | Token stream, grammar hoặc parser options | Token fingerprint và grammar version. |
| Semantic cache | AST, symbol interface, type environment hoặc imports | Dependency graph và semantic version. |
| IR cache | Semantic model, lowering rules hoặc target configuration | Fingerprint của IR inputs và pass versions. |
| Artifact cache | IR, compiler backend, flags, dependencies | Content hash và build key. |
| Runtime result cache | Arguments, data snapshot, policy, permissions, clock | Key đầy đủ, dependency versions, TTL hoặc explicit invalidation. |
| Metadata cache | Schema, service registry, capability metadata | Version, event invalidation hoặc TTL. |

### Không invalidation quá ít

Nếu một phụ thuộc thay đổi nhưng cache entry vẫn được dùng, hệ thống có thể trả kết quả sai. Đây là lỗi correctness và có thể gây hậu quả nghiệp vụ.

### Không invalidation quá nhiều

Nếu mọi thay đổi đều xóa toàn bộ cache, hệ thống vẫn đúng nhưng mất lợi ích hiệu năng. Dependency tracking tốt giúp giới hạn phạm vi phải tính lại.

### Invalidation phải nhất quán với giao dịch

Nếu dữ liệu được cập nhật trong database nhưng sự kiện invalidation bị mất, cache có thể giữ giá trị cũ. Có thể dùng transactional outbox, version check khi đọc hoặc cơ chế đồng bộ khác để bảo đảm cập nhật dữ liệu và thông báo invalidation không bị tách rời ngoài ý muốn.

## 10. Memoization – cache kết quả hàm

**Memoization** là kỹ thuật lưu kết quả của một hàm theo các đối số để lần gọi sau với cùng đối số có thể trả kết quả đã lưu.

Ví dụ:

~~~java
Map<Key, Result> cache = new HashMap<>();

Result evaluate(Key key) {
    Result cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    Result result = compute(key);
    cache.put(key, result);
    return result;
}
~~~

Đây là minh họa đơn giản; triển khai thực tế cần xử lý null result, exception, concurrency, eviction và invalidation.

### Điều kiện an toàn

Memoization phù hợp nhất với hàm thuần (*pure function*):

- Cùng đối số tạo cùng kết quả.
- Hàm không đọc trạng thái ẩn có thể thay đổi.
- Hàm không tạo tác dụng phụ cần thực hiện ở mỗi lần gọi.
- Kết quả không phụ thuộc thời điểm hoặc môi trường chưa được đưa vào đối số.

Ví dụ:

~~~text
calculateTax(amount, taxRate)
~~~

Nếu phép tính thuế chỉ phụ thuộc hai đối số và quy tắc số học cố định, kết quả có thể memoize.

Ngược lại:

~~~text
isEligible(customerId)
~~~

Nếu hàm đọc trạng thái tài khoản hiện tại từ database, cùng `customerId` có thể cho kết quả khác theo thời gian. Muốn cache, cần đưa snapshot/version trạng thái vào key hoặc sử dụng invalidation đáng tin cậy.

### Memoization đệ quy

Memoization có thể tránh tính lại các bài toán con trong hàm đệ quy. Ví dụ, một evaluator xử lý biểu thức con dùng chung có thể cache kết quả theo node identity và environment fingerprint. Cần chú ý node identity không đủ nếu cùng AST node được đánh giá trong hai environment khác nhau.

### Memoization theo AST node

Một interpreter có thể lưu kết quả cho node thuần:

~~~text
cacheKey = (nodeId, environmentVersion)
~~~

Nếu environment thay đổi, cache cũ không còn phù hợp. Nếu node tham chiếu biến cục bộ, key cần phản ánh binding hoặc giá trị biến liên quan, không chỉ ID của node.

## 11. Cache kết quả biểu thức trong interpreter

Interpreter có thể đánh giá cùng một biểu thức nhiều lần trong một lần chạy hoặc giữa nhiều lần chạy.

Ví dụ:

~~~text
let subtotal = sum(order.items.price);
let tax = subtotal * taxRate;
let total = subtotal + tax;
~~~

Nếu `subtotal` được tham chiếu nhiều lần và dữ liệu `order.items` không thay đổi trong execution context, interpreter có thể tính một lần rồi tái sử dụng.

### Cache theo evaluation context

Một cache nội bộ cho một lần thực thi có thể dùng key gồm node ID và environment frame. Khi scope kết thúc, cache có thể được giải phóng cùng frame. Cách này giới hạn lifetime và tránh vô tình chia sẻ kết quả giữa các lần chạy độc lập.

### Cache biểu thức thuần

Interpreter có thể đánh dấu AST node hoặc function là pure. Chỉ các node được chứng minh không có tác dụng phụ mới được đưa vào memoization tự động. Nếu người dùng khai báo purity nhưng hàm thực tế đọc dữ liệu ngoài hoặc ghi trạng thái, compiler cần có cơ chế ngăn hoặc phát hiện vi phạm hợp đồng.

### Cache biểu thức có dependency

Nếu biểu thức đọc biến, thuộc tính hoặc dữ liệu context, cache entry có thể ghi lại các dependency đã đọc. Khi một dependency thay đổi, entry bị invalidated. Đây là mô hình gần với reactive computation.

### Không cache hành động có tác dụng phụ

Một lời gọi như:

~~~text
sendEmail(customer.email, message);
~~~

không nên bị memoize chỉ vì cùng đối số. Người dùng mong đợi mỗi lần gọi hợp lệ đều gửi email. Cache kết quả của hành động có thể khiến tác dụng phụ bị bỏ qua. Nếu mục tiêu là tránh thực hiện trùng do retry, cần dùng idempotency key và hợp đồng idempotent của action, không áp dụng memoization một cách ngầm định.

## 12. Cache kết quả rule engine

Rule engine có thể đánh giá một tập quy tắc trên dữ liệu nghiệp vụ. Kết quả có thể được cache nếu đầu vào và mọi dữ liệu ảnh hưởng đều được xác định.

Ví dụ:

~~~text
decision = evaluatePolicy(
    policy = OrderApproval@v4,
    order = Order#O100,
    customer = Customer#C20
);
~~~

Cache key có thể gồm policy fingerprint, order snapshot version, customer snapshot version và các context liên quan.

### Cache decision result

Một decision result có thể chứa:

~~~text
DecisionResult
  outcome
  matchedRules
  explanation
  dependencyVersions
  evaluatedAt
~~~

Lưu `matchedRules` và explanation giúp hệ thống giải thích quyết định đã được tạo như thế nào. `evaluatedAt` hữu ích cho audit nhưng không nhất thiết là đầu vào của kết quả.

### Rule có trạng thái

Nếu rule cập nhật dữ liệu, phát sự kiện hoặc gọi service, không nên cache toàn bộ lần thực thi như một phép tính thuần. Có thể cache phần phân tích hoặc phần quyết định thuần, rồi thực hiện action riêng theo execution ID và idempotency contract.

### Conflict resolution

Nếu nhiều rule cùng khớp, kết quả phụ thuộc priority, thứ tự tie-break và phiên bản tập rule. Những yếu tố này phải được đưa vào fingerprint. Nếu thứ tự rule được lấy từ collection không ổn định, cache có thể lưu một kết quả tình cờ và che giấu sự bất định của engine.

## 13. Cache kết quả truy vấn

DSL truy vấn có thể cache kết quả khi truy vấn lặp lại thường xuyên.

~~~text
select order from Orders
where order.status == PAID
order by order.createdAt descending;
~~~

Kết quả phụ thuộc vào:

- Nội dung và cấu trúc truy vấn.
- Tham số truy vấn.
- Snapshot dữ liệu hoặc version của các bảng/collection.
- Quyền truy cập và tenant.
- Thứ tự sắp xếp và collation.
- Locale hoặc timezone nếu biểu thức sử dụng chúng.
- Pagination, cursor và consistency level.

### Cache theo query fingerprint

Query có thể được chuẩn hóa thành AST rồi tạo fingerprint. Các tham số có thể nằm riêng trong key để dùng lại query plan hoặc nằm trong key kết quả tùy loại cache.

### Query plan cache và result cache

**Query plan cache** lưu kế hoạch thực thi đã tối ưu. Cùng cấu trúc truy vấn có thể dùng chung plan với nhiều giá trị tham số nếu kiểu và thống kê phù hợp.

**Query result cache** lưu tập kết quả thực tế. Kết quả phụ thuộc vào dữ liệu và quyền, nên invalidation phức tạp hơn.

Không nên nhầm hai cache này. Một query plan vẫn có thể hợp lệ khi dữ liệu thay đổi; result cache có thể phải invalidated ngay khi dữ liệu liên quan đổi.

### Pagination và thứ tự ổn định

Nếu truy vấn không có thứ tự xác định, cache có thể trả cùng một thứ tự tình cờ trong một thời gian nhưng kết quả đó không phải bảo đảm ngữ nghĩa. Khi phân trang, nên dùng khóa sắp xếp ổn định và snapshot/cursor phù hợp. Cache key cần bao gồm page hoặc cursor nếu lưu kết quả từng trang.

## 14. Cache kết quả compile và build

Build cache lưu artifact được tạo từ source và các phụ thuộc. Đây là nền tảng của incremental build và remote build cache.

### Cache key cho compilation unit

Một khóa compile có thể được tạo từ:

~~~text
compileKey = hash(
    sourceFingerprint,
    importedInterfaceFingerprints,
    compilerVersion,
    languageVersion,
    compilerFlags,
    targetPlatform,
    pluginFingerprints
)
~~~

Nếu mọi thành phần này giống nhau và compiler có tính tái lập, artifact đã cache có thể được dùng lại.

### Phân biệt interface và implementation dependency

Nếu module A chỉ dùng public interface của module B, thay đổi nội bộ B không nhất thiết buộc A compile lại. Nếu compiler inline hàm của B vào A, nội dung implementation có thể là dependency của A. Dependency tracking cần phản ánh cách compiler thực sự dùng module.

### Artifact cache

Artifact có thể là:

- Token stream hoặc AST đã serialize.
- Semantic model hoặc symbol index.
- IR sau lowering.
- Bytecode hoặc object file.
- Mã nguồn được sinh.
- Metadata build và dependency manifest.

Artifact cần có schema/version để tránh deserialize bằng cấu trúc không tương thích. Cache entry nên được xác minh trước khi dùng, đặc biệt khi được tải từ remote cache.

### Remote cache

Remote cache cho phép nhiều máy build chia sẻ artifact. Lợi ích lớn khi CI thường xuyên build cùng module hoặc các nhánh có nhiều dependency chung. Tuy nhiên, cần xác thực artifact, kiểm soát quyền đọc/ghi, phân vùng project và bảo vệ tính toàn vẹn của key.

## 15. Cache âm tính (negative caching)

Cache không chỉ lưu kết quả thành công. Hệ thống có thể lưu cả kết quả “không tìm thấy” hoặc lỗi có thể lặp lại, gọi là negative caching.

Ví dụ, resolver tra một module và xác định module đó không tồn tại trong registry ở thời điểm hiện tại. Nếu nhiều request lặp lại cùng truy vấn, có thể cache kết quả không tìm thấy trong thời gian ngắn.

### Khi nào hữu ích?

- Giảm truy vấn lặp đến registry hoặc service discovery.
- Tránh liên tục phân giải một tên sai trong IDE.
- Giảm tải khi dependency không tồn tại hoặc bị từ chối rõ ràng.
- Hạn chế truy vấn lặp với ID không hợp lệ.

### Rủi ro

Nếu module vừa được publish nhưng negative cache vẫn còn, hệ thống có thể tiếp tục báo không tìm thấy. Vì vậy, negative entry thường cần TTL ngắn, version namespace hoặc invalidation khi registry thay đổi.

### Phân biệt lỗi tạm thời và lỗi xác định

Không nên cache timeout, network error hoặc lỗi xác thực tạm thời như thể đích chắc chắn không tồn tại. Kết quả lỗi cần có loại và chính sách cache riêng. Một số lỗi có thể cache ngắn để bảo vệ hệ thống; một số lỗi không nên cache vì có thể được khắc phục ngay sau đó.

## 16. TTL, eviction và giới hạn bộ nhớ

Cache có dung lượng hữu hạn. Nếu không giới hạn, cache có thể làm tăng bộ nhớ đến mức gây áp lực GC hoặc làm tiến trình hết bộ nhớ.

### TTL

TTL xác định thời gian entry được giữ hoặc được xem là còn mới. TTL phù hợp với dữ liệu ngoài thay đổi theo thời gian nhưng không có cơ chế notification đáng tin cậy.

Các lựa chọn:

- **Expire after write:** hết hạn sau một khoảng kể từ lúc ghi.
- **Expire after access:** hết hạn sau một khoảng không được truy cập.
- **Refresh after write:** cho phép làm mới nền sau một khoảng nhưng có thể tiếp tục trả giá trị cũ trong thời gian refresh.
- **No time expiry:** giữ đến khi invalidation hoặc eviction; phù hợp với artifact bất biến theo content hash.

TTL không thay thế dependency version khi cần tính đúng đắn tức thời.

### Eviction policy

| Chính sách | Cách hoạt động | Khi phù hợp |
|---|---|---|
| LRU | Loại mục ít được truy cập gần đây nhất. | Workload có tính locality theo thời gian. |
| LFU | Loại mục có tần suất truy cập thấp. | Có nhóm kết quả được dùng thường xuyên ổn định. |
| FIFO | Loại mục được thêm sớm nhất. | Chính sách đơn giản, chi phí thấp. |
| Size-based | Ưu tiên loại mục lớn hoặc theo trọng số dung lượng. | Entry có kích thước rất khác nhau. |
| Admission policy | Chỉ cache mục có khả năng được dùng lại. | Tránh cache các kết quả dùng một lần. |

### Giới hạn theo số lượng và dung lượng

Cache có thể giới hạn số entry, tổng byte hoặc kích thước từng entry. Với AST lớn, giới hạn theo số lượng không phản ánh đúng bộ nhớ. Cần ước tính hoặc đo kích thước thực tế.

### Cache nhiều tầng

Một hệ thống có thể có L1 cache trong tiến trình và L2 cache dùng chung hoặc từ xa. L1 nhanh nhưng có phạm vi hẹp; L2 có thể chia sẻ giữa worker nhưng thêm độ trễ mạng và yêu cầu serialization. Cần xác định nguồn sự thật và cách invalidation giữa các tầng.

## 17. Cache cục bộ và cache phân tán

### In-process cache

Cache trong bộ nhớ của một tiến trình có độ trễ thấp và dễ tích hợp. Nó thường được dùng cho token, AST, symbol, query plan hoặc memoization trong một execution context.

Ưu điểm:

- Tra cứu nhanh.
- Không cần network hoặc serialization.
- Dễ gắn với vòng đời tài liệu hoặc phiên chạy.

Hạn chế:

- Không chia sẻ giữa nhiều process.
- Mất khi tiến trình khởi động lại.
- Mỗi instance có thể giữ một phiên bản cache khác nhau.
- Bộ nhớ cạnh tranh với heap của compiler/interpreter.

### Shared cache

Shared cache cho phép nhiều worker dùng chung kết quả. Nó phù hợp với artifact build hoặc metadata có thể chia sẻ theo key.

Các vấn đề cần xử lý:

- Network latency và lỗi kết nối.
- Serialization format và schema version.
- Quyền truy cập, tenant isolation và encryption.
- Đồng bộ invalidation giữa các worker.
- Cache entry hỏng hoặc bị ghi một phần.
- Tranh chấp khi nhiều worker cùng tạo một key.

### Remote build cache

Remote build cache thường dùng key content-addressed. Worker tính key, kiểm tra cache từ xa, tải artifact nếu hit hoặc build và upload nếu miss. Artifact cần được xác thực bằng checksum và metadata tương ứng với compiler/toolchain.

### Không tin cache từ xa một cách mù quáng

Một cache dùng chung có thể là nguồn dữ liệu không đáng tin cậy nếu nhiều bên có quyền ghi. Cần xác minh checksum, chữ ký hoặc nguồn tạo artifact theo mô hình bảo mật của hệ thống. Không deserialize dữ liệu tùy ý bằng một định dạng có thể thực thi mã nếu chưa xác thực nguồn.

## 18. Đồng thời và cache stampede

Khi nhiều yêu cầu cùng cần một key chưa có, chúng có thể cùng tính một kết quả tốn kém. Hiện tượng này được gọi là cache stampede hoặc thundering herd.

Ví dụ, 100 request cùng yêu cầu compile một module. Nếu cache miss làm cả 100 worker cùng compile và ghi kết quả, tài nguyên bị lãng phí.

### Single-flight

Một cơ chế single-flight cho phép chỉ một worker tính key; các worker khác chờ kết quả của cùng phép tính.

~~~text
getOrCompute(key):
    if cache contains key:
        return cache[key]

    if computation for key exists:
        wait for that computation
        return its result

    register computation for key
    result = compute()
    cache[key] = result
    publish result to waiters
    remove in-flight marker
    return result
~~~

Triển khai cần xử lý cả trường hợp compute thất bại để waiter không chờ vô hạn và marker không bị kẹt.

### Atomic put-if-absent

Trong môi trường nhiều tiến trình, thao tác kiểm tra rồi ghi có thể xảy ra race. Có thể dùng lock theo key, distributed lock hoặc primitive atomic `put-if-absent`. Lock cần có timeout, xử lý worker chết và tránh deadlock.

### Nhiều worker tính trùng

Với phép tính rẻ hoặc khi lock phức tạp hơn compute, cho phép nhiều worker tính song song rồi chỉ một kết quả được commit có thể đơn giản hơn. Cách này cần bảo đảm phép tính thuần và kết quả tương đương.

### Cache entry bất biến

Artifact và kết quả nên được ghi theo cách atomic: tạo hoàn chỉnh rồi publish key. Không để reader nhìn thấy entry đang ghi dở. Với file cache, có thể ghi file tạm rồi đổi tên nguyên tử nếu filesystem hỗ trợ.

## 19. Cache lỗi và exception

Một quyết định quan trọng là có cache lỗi hay không. Không phải lỗi nào cũng có cùng tính chất.

### Lỗi xác định

Ví dụ compiler phát hiện kiểu không tương thích trong một source snapshot bất biến. Diagnostic đó có thể được cache cùng fingerprint của nguồn, grammar, compiler và dependency. Khi các thành phần không đổi, lỗi vẫn còn hợp lệ.

### Lỗi tạm thời

Timeout của dịch vụ ngoài hoặc lỗi kết nối database không nên được cache dài như một kết quả nghiệp vụ. Lần thử sau có thể thành công.

### Exception từ hàm thuần

Nếu một hàm thuần với cùng đối số luôn ném cùng loại lỗi theo ngữ nghĩa, có thể cache lỗi nếu hợp đồng yêu cầu. Nhưng cần quyết định có lưu stack trace, thông tin runtime và thời điểm hay không. Stack trace có thể phụ thuộc call site nên không phải lúc nào cũng tái sử dụng được nguyên vẹn.

### Negative result và exception

Kết quả rỗng (“không có đối tượng phù hợp”) khác với exception (“không thể truy vấn”). Cache nên biểu diễn riêng hai trạng thái để không biến lỗi vận hành thành kết quả nghiệp vụ hợp lệ.

### Diagnostic cache

Diagnostic compile có thể cache theo source/dependency fingerprint. Khi trả lại, vị trí cần gắn với đúng snapshot hoặc được ánh xạ sang version mới. Không được hiển thị diagnostic cũ ở offset không còn tương ứng sau chỉnh sửa.

## 20. Tính thuần, tác dụng phụ và an toàn của cache

Một phép tính chỉ có thể được tái sử dụng nếu kết quả phụ thuộc đầy đủ vào những gì được biểu diễn trong key và việc bỏ qua lần thực thi mới không làm mất tác dụng phụ cần thiết.

### Hàm thuần

Hàm thuần không đọc hoặc ghi trạng thái ẩn và trả cùng kết quả với cùng đối số. Đây là ứng viên tốt cho memoization.

~~~text
function calculateTotal(items, taxRate) pure {
    return sum(items.price) * (1 + taxRate);
}
~~~

Nếu `items` và `taxRate` bất biến hoặc được định danh bằng fingerprint ổn định, kết quả có thể cache.

### Hàm đọc trạng thái ngoài

~~~text
function currentCreditLimit(customerId) {
    return database.readCreditLimit(customerId);
}
~~~

Hàm này phụ thuộc database. Có thể cache nếu key bao gồm version hoặc snapshot liên quan và invalidation được đồng bộ với cập nhật dữ liệu.

### Hàm có tác dụng phụ

~~~text
function chargeCard(payment) {
    paymentGateway.charge(payment);
}
~~~

Không được bỏ qua lời gọi này chỉ vì trước đó đã có kết quả cho cùng `payment`. Cache có thể được dùng để lưu trạng thái của một thao tác theo idempotency key nếu API định nghĩa hành vi đó, nhưng đây là cơ chế chống thực hiện trùng chứ không phải memoization thuần.

### DSL khai báo purity

DSL có thể cho phép đánh dấu hàm `pure`, `deterministic` hoặc `cacheable`. Compiler nên kiểm tra các thuộc tính có thể suy ra tĩnh như việc gọi hàm có tác dụng phụ, đọc clock hoặc truy cập mutable global. Với các dependency không thể chứng minh tĩnh, có thể yêu cầu khai báo rõ hoặc từ chối cache tự động.

Không nên tin một annotation purity nếu runtime cho phép hàm gọi dịch vụ hoặc đọc trạng thái toàn cục mà không được theo dõi.

## 21. Cache phụ thuộc thời gian, ngẫu nhiên và locale

Một số đầu vào dễ bị bỏ sót vì không xuất hiện trong tham số hàm.

### Thời gian

~~~text
if order.createdAt < now() - 30 days then markOverdue;
~~~

Nếu kết quả được cache chỉ theo `order.id`, quyết định có thể sai sau khi thời gian vượt qua ngưỡng 30 ngày. Cách xử lý có thể là:

- Đưa instant đánh giá vào key.
- Cache đến thời điểm ranh giới kế tiếp và đặt TTL tương ứng.
- Không cache kết quả có phụ thuộc thời gian động.
- Dùng một clock snapshot cho cả execution và ghi lại snapshot đó.

### Số ngẫu nhiên

~~~text
assignAgent = chooseRandom(availableAgents);
~~~

Nếu seed không được đưa vào key, cache có thể biến hành vi ngẫu nhiên thành một lựa chọn cố định. Điều này có thể đúng hoặc sai tùy mục tiêu DSL. Nếu muốn tái lập mô phỏng, seed và thuật toán random cần được cố định. Nếu muốn mỗi lần phân công là một lựa chọn mới, không nên cache kết quả giữa các lần chạy.

### Locale và timezone

Một biểu thức định dạng ngày hoặc số có thể phụ thuộc locale/timezone. Nếu kết quả hiển thị được cache theo giá trị nhưng không có locale, người dùng ở các locale khác nhau có thể nhận cùng chuỗi định dạng sai.

### Feature flags và cấu hình

Feature flag, tenant config và runtime options có thể thay đổi nhánh thực thi. Nếu chúng ảnh hưởng kết quả, cần đưa version/fingerprint của cấu hình vào key hoặc invalidation khi flag đổi.

## 22. Cache và bảo mật

Cache có thể làm rò rỉ dữ liệu nếu kết quả được chia sẻ giữa các người dùng hoặc tenant mà không phân vùng đúng.

### Tenant isolation

Nếu hai tenant có cùng `customerId` nhưng dữ liệu khác nhau, cache key chỉ gồm ID có thể trả kết quả của tenant này cho tenant kia. Key phải chứa tenant identity hoặc namespace tương đương nếu kết quả phụ thuộc tenant.

### User permissions

Kết quả truy vấn có thể phụ thuộc quyền người dùng. Nếu người dùng A được xem dữ liệu mà B không được phép xem, cache result không thể chỉ được key theo câu truy vấn. Có thể key theo security principal/permission fingerprint hoặc cache dữ liệu thô rồi lọc quyền ở bước sau nếu điều đó an toàn và đúng kiến trúc.

### Secrets và thông tin nhạy cảm

Không nên đưa secret trực tiếp vào cache key có thể quan sát trong log. Có thể dùng fingerprint an toàn hoặc định danh credential version. Cached value cần được bảo vệ tương ứng với độ nhạy dữ liệu gốc.

### Cache poisoning

Nếu người dùng không tin cậy có thể ghi artifact hoặc result vào shared cache, họ có thể cố tình tạo entry độc hại cho key mà người khác sẽ dùng. Cần xác thực người ghi, kiểm tra hash, phân quyền namespace và chỉ dùng artifact có nguồn gốc tin cậy.

### Eviction và xóa dữ liệu

Khi người dùng yêu cầu xóa dữ liệu, cần xem cache là một bản sao dữ liệu. Chính sách retention và deletion phải bao gồm các cache layer, backup và remote cache theo yêu cầu hệ thống. Không nên giữ dữ liệu nhạy cảm lâu hơn mục đích cần thiết.

## 23. Cache và tính nhất quán dữ liệu

Cache thường tạo ra một bản sao của kết quả hoặc dữ liệu đã đọc. Bản sao đó có thể không đồng bộ ngay với nguồn dữ liệu.

### Cache-aside

Trong mô hình cache-aside, ứng dụng kiểm tra cache trước; nếu miss thì đọc nguồn dữ liệu, tính kết quả và ghi cache. Khi cập nhật nguồn, ứng dụng thường invalidates cache liên quan.

~~~text
read(key):
    value = cache.get(key)
    if value exists:
        return value

    value = source.read(key)
    cache.put(key, value)
    return value
~~~

### Write-through

Write-through cập nhật nguồn dữ liệu và cache theo cùng thao tác logic. Nó giúp cache cập nhật ngay nhưng cần xử lý lỗi khi một phía thành công còn phía kia thất bại.

### Write-behind

Write-behind ghi vào cache trước rồi cập nhật nguồn bất đồng bộ. Cách này có thể tăng throughput nhưng tạo khoảng thời gian dữ liệu chưa được ghi bền vững. Nó cần hàng đợi, retry và cơ chế phục hồi.

### Stale-while-revalidate

Hệ thống có thể trả kết quả cũ trong lúc làm mới nền. Cách này giảm latency nhưng chỉ phù hợp khi nghiệp vụ chấp nhận dữ liệu hơi cũ. Với quyết định quyền, số dư, giá trị thanh toán hoặc trạng thái phê duyệt, cần chính sách nghiêm ngặt hơn.

### Chọn consistency level

DSL hoặc runtime nên phân biệt các yêu cầu:

- Kết quả phải phản ánh dữ liệu mới nhất.
- Kết quả được phép cũ tối đa một khoảng thời gian.
- Kết quả phải nhất quán theo một snapshot.
- Kết quả chỉ cần nhất quán cuối cùng.

Không nên chọn TTL chỉ vì tiện; nó phải phù hợp với yêu cầu nghiệp vụ.

## 24. Cache theo phiên bản và cache bất biến

Một chiến lược mạnh là gắn cache entry với phiên bản bất biến của đầu vào. Thay vì sửa một cache key hiện có, mỗi version tạo key mới.

Ví dụ:

~~~text
OrderApproval@v4 + OrderSnapshot#O100-v17
~~~

Kết quả cho cặp phiên bản này được lưu riêng. Khi policy chuyển sang `v5` hoặc order snapshot chuyển sang `v18`, key mới được tạo. Entry cũ vẫn có thể dùng để tái hiện quyết định lịch sử.

### Lợi ích

- Dễ tái lập quyết định cũ.
- Không cần sửa cache entry bất biến.
- Có thể chia sẻ artifact theo content hash.
- Dễ kiểm tra nguồn gốc của kết quả.

### Chi phí

- Số entry tăng theo số version.
- Cần eviction và retention.
- Cần quản lý vòng đời version và dữ liệu liên quan.
- Không phù hợp với dữ liệu thay đổi liên tục nếu mỗi thay đổi tạo một key mới và không có giới hạn.

## 25. Cache cho compiler gia tăng

Compiler gia tăng chỉ xử lý lại phần dự án bị ảnh hưởng. Cache là một trong các cơ chế giúp giữ kết quả của những phần không đổi.

### Cache theo compilation unit

Mỗi module hoặc compilation unit có thể có entry riêng. Khi source và dependency fingerprint không đổi, compiler dùng lại kết quả parse, semantic hoặc artifact tương ứng.

### Phân tích dependency

Compiler cần xác định module nào phụ thuộc vào interface nào. Khi public interface thay đổi, các module phụ thuộc có thể phải compile lại. Khi chỉ implementation thay đổi, phạm vi invalidation có thể nhỏ hơn nếu compiler không inline hoặc phụ thuộc nội dung implementation.

### Cache nhiều giai đoạn

Có thể cache:

- Token stream sau lexing.
- CST/AST sau parsing.
- Symbol table sau name resolution.
- Type information sau type checking.
- IR sau lowering.
- Artifact cuối sau code generation.

Mỗi tầng có fingerprint và version riêng. Một thay đổi chỉ làm invalidation từ tầng đầu tiên bị ảnh hưởng trở đi.

### Cache không thay thế dependency analysis

Nếu compiler không biết module A phụ thuộc B, nó không thể xác định khi nào kết quả A hết hiệu lực. Lưu artifact theo hash nhưng hash không bao gồm B vẫn tạo ra lỗi cache. Dependency analysis là nền tảng correctness của incremental build.

## 26. Cache kết quả trong môi trường IDE

IDE thường xử lý tài liệu chưa hoàn chỉnh và nhiều version liên tiếp. Cache trong IDE cần gắn với document version, workspace, compiler settings và dependency state.

### Cache parse và semantic diagnostics

Khi người dùng sửa một biểu thức, IDE có thể tái sử dụng phần AST không đổi và cache kết quả phân tích của các node không bị ảnh hưởng. Nhưng một thay đổi khai báo có thể ảnh hưởng nhiều tham chiếu ở nơi khác.

### Cache completion

Gợi ý completion có thể cache theo:

- Vị trí con trỏ và cú pháp xung quanh.
- Scope và symbol table version.
- Module/import graph version.
- Kiểu biểu thức hoặc expected type.
- Document version hoặc một fingerprint của vùng liên quan.

Nếu scope thay đổi, completion cũ có thể gợi ý tên không còn hợp lệ.

### Cache hover và Go to Definition

Kết quả hover hoặc definition có thể được cache theo symbol identity và semantic snapshot. Nếu symbol bị rename hoặc module bị reload, cache cần cập nhật.

### Bỏ kết quả lỗi thời

Một tác vụ phân tích version 10 có thể hoàn tất sau khi editor đã ở version 12. Kết quả version 10 không nên ghi đè cache hoặc diagnostics của version 12. Cần version check khi publish kết quả và khi ghi cache.

## 27. Cache và serialization

Cache tồn tại trong bộ nhớ có thể lưu trực tiếp object. Cache trên đĩa hoặc từ xa cần serialize dữ liệu.

### Schema version

Nếu cấu trúc AST hoặc IR thay đổi giữa các phiên bản compiler, artifact cũ có thể không deserialize được hoặc có thể bị diễn giải sai. Mỗi cache entry nên lưu schema version hoặc compiler format version.

### Serialization ổn định

Nếu hash được tính từ serialization, định dạng cần ổn định: thứ tự field, encoding, representation của số, map và metadata phải được quy định. Serialization không ổn định có thể tạo key khác nhau cho cùng mô hình hoặc key giống nhau cho nội dung không tương đương nếu field bị bỏ sót.

### Không cache đối tượng có trạng thái mutable chưa kiểm soát

Nếu nhiều request dùng chung một AST mutable hoặc collection mutable từ cache, một request có thể thay đổi kết quả của request khác. Có thể dùng object bất biến, defensive copy hoặc ownership rõ ràng.

### Artifact integrity

Cache entry nên có checksum hoặc xác thực tương ứng. Nếu dữ liệu bị hỏng, hệ thống nên loại entry và tính lại thay vì tiếp tục dùng artifact không đầy đủ.

## 28. Cache và lỗi vận hành

Cache là một tối ưu, vì vậy hệ thống thường cần hành vi fallback khi cache không khả dụng.

### Cache miss bình thường

Miss phải dẫn đến tính lại nếu nguồn dữ liệu còn sẵn sàng. Nó không nên bị coi là lỗi ứng dụng.

### Cache service không khả dụng

Nếu remote cache lỗi, build có thể tiếp tục compile cục bộ nếu chính sách cho phép. Với cache kết quả runtime, có thể đọc nguồn hoặc tính lại. Tuy nhiên, nếu cache là nơi lưu trạng thái duy nhất thay vì bản sao có thể tái tạo, nó không còn là cache thuần và cần độ bền dữ liệu tương ứng.

### Cache entry hỏng

Nếu deserialize thất bại hoặc checksum sai, hệ thống nên ghi nhận lỗi, loại entry và fallback. Không nên lặp lại việc tải cùng một entry hỏng vô hạn.

### Fallback và correctness

Fallback phải thực hiện cùng phép tính theo cùng đầu vào hiệu lực. Nếu fallback bỏ qua một dependency hoặc dùng nguồn dữ liệu khác, kết quả có thể không tương đương.

## 29. Đo lường hiệu quả cache

Không nên đánh giá cache chỉ bằng tỷ lệ hit. Một cache có hit rate cao nhưng lưu kết quả nhỏ hoặc có chi phí kiểm tra lớn vẫn có thể không mang lại lợi ích.

Các chỉ số nên theo dõi:

- **Hit rate:** tỷ lệ request được phục vụ từ cache.
- **Miss rate:** tỷ lệ request phải tính lại.
- **Latency saved:** thời gian tiết kiệm được khi hit.
- **Compute avoided:** số lần hoặc lượng công việc tính toán đã tránh.
- **Eviction rate:** tốc độ entry bị loại do giới hạn dung lượng.
- **Invalidation count:** số entry bị vô hiệu do dependency thay đổi.
- **Stale result incidents:** số trường hợp phát hiện dùng kết quả lỗi thời.
- **Memory footprint:** dung lượng cache đang sử dụng.
- **Remote transfer cost:** thời gian và byte tải artifact từ cache từ xa.
- **Duplicate computation:** số lần cùng key bị tính song song.

### Ví dụ tính hit rate

Nếu có 1.000 yêu cầu và 820 yêu cầu được phục vụ bằng cache hit:

~~~text
hitRate = 820 / 1000 = 0.82 = 82%
~~~

Hit rate 82% chỉ nói rằng phần lớn yêu cầu tìm thấy entry. Cần so sánh latency, kích thước kết quả và correctness để kết luận cache có hiệu quả.

### Theo dõi theo cache layer

Không nên gộp mọi cache thành một số duy nhất. Token cache có thể hit cao nhưng tiết kiệm ít thời gian; artifact cache có thể hit thấp hơn nhưng tiết kiệm nhiều phút build. Metrics nên tách theo loại và workload.

## 30. Ví dụ triển khai cache an toàn trong Java

Giả sử một compiler có thể cache kết quả phân tích một module theo fingerprint. Một key bất biến có thể được mô hình hóa:

~~~java
record CompileKey(
    String sourceHash,
    String compilerVersion,
    String languageVersion,
    String optionsHash,
    String dependenciesHash
) {}

record CompileResult(
    byte[] artifact,
    String artifactHash
) {}
~~~

Một cache đơn giản:

~~~java
final class CompilationCache {
    private final java.util.concurrent.ConcurrentMap<CompileKey, CompileResult>
        entries = new java.util.concurrent.ConcurrentHashMap<>();

    CompileResult getOrCompile(
            CompileKey key,
            java.util.function.Supplier<CompileResult> compiler) {
        return entries.computeIfAbsent(key, ignored -> compiler.get());
    }
}
~~~

Ví dụ này minh họa việc dùng key gồm fingerprint đầu vào và map an toàn luồng. Trong hệ thống thực tế, `computeIfAbsent` cần được cân nhắc nếu compilation chạy lâu, có thể đệ quy hoặc cần hủy tác vụ; không phải mọi cache implementation đều nên chạy tác vụ nặng ngay bên trong hàm mapping. Cần thêm eviction, giới hạn dung lượng, xử lý exception và persistence nếu cần.

### Không dùng mutable array làm identity của key

Record ở trên chứa `String`, nên equality dựa trên giá trị chuỗi. Nếu key chứa `byte[]`, equality mặc định của array là identity, không phải so sánh nội dung. Có thể dùng immutable wrapper, hash string hoặc kiểu có `equals`/`hashCode` theo nội dung.

### Cache result null

Nếu phép compile có thể trả `null`, `computeIfAbsent` không lưu kết quả null theo hợp đồng của map. Nên dùng kiểu kết quả tường minh như `Optional`, sealed result hoặc wrapper để phân biệt thành công, không có kết quả và lỗi.

## 31. Ví dụ cache kết quả biểu thức DSL

Giả sử DSL có hàm thuần tính phí:

~~~text
function calculateShipping(weight, rate) pure {
    return weight * rate;
}
~~~

Một runtime có thể memoize theo cặp đối số đã chuẩn hóa:

~~~text
key = (weight, rate)

if cache contains key:
    return cache[key]

result = weight * rate
cache[key] = result
return result
~~~

Nếu `weight` và `rate` là kiểu số thập phân có equality và rounding được định nghĩa, cache có thể dùng key theo giá trị chuẩn hóa. Nếu chúng là floating point, cần quyết định cách xử lý `NaN`, `-0.0`, precision và equality. Không nên tự làm tròn key chỉ để tăng hit rate nếu điều đó có thể gộp hai đầu vào tạo kết quả khác nhau.

### Khi rate thay đổi

Vì `rate` nằm trong key, thay đổi rate tự tạo key mới. Không cần xóa mọi entry cũ ngay lập tức; eviction có thể thu hồi chúng sau. Nếu rate được đọc ẩn từ một bảng giá, bảng giá version phải được thêm vào key hoặc được ghi nhận như dependency.

### Khi hàm không còn pure

Nếu hàm được sửa để ghi log, đọc đồng hồ hoặc truy cập dịch vụ, cache có thể bỏ qua hành vi cần thực hiện. Compiler cần cập nhật purity metadata và invalidation của artifact liên quan khi thay đổi semantics.

## 32. Cache kết quả quyết định và audit trail

Trong DSL nghiệp vụ, cache một quyết định có thể ảnh hưởng trực tiếp đến việc chấp nhận, từ chối hoặc định tuyến giao dịch. Vì vậy, kết quả cache nên lưu cả nguồn gốc và dependency snapshot cần thiết.

Một bản ghi quyết định có thể gồm:

~~~text
CachedDecision
  decisionId
  outcome
  policyFingerprint
  inputSnapshotId
  dependencyVersions
  matchedRuleIds
  explanation
  evaluatedAt
~~~

Khi cần giải thích một quyết định cũ, hệ thống có thể biết policy version và snapshot nào đã tạo kết quả. Nếu quyết định được cache để phục vụ request mới, cần xác nhận input snapshot và quyền hiện tại phù hợp với key.

### Cache không thay thế audit log

Cache có thể bị eviction, xóa hoặc làm mới. Nó không nên là nơi duy nhất lưu bằng chứng nghiệp vụ bắt buộc. Nếu cần audit, hãy ghi decision event hoặc bản ghi bền vững theo chính sách lưu trữ riêng.

### Phân biệt replay và cache hit

Replay thực hiện lại logic trên dữ liệu lịch sử để tái tạo trạng thái hoặc xác minh kết quả. Cache hit chỉ trả kết quả đã lưu. Hai thao tác có mục tiêu khác nhau; một cache hit không chứng minh logic hiện tại vẫn tạo cùng kết quả nếu được chạy lại.

## 33. Cache và tính tái lập của build

Cache hiệu quả nhất khi cùng đầu vào tạo cùng artifact. Nếu compiler sinh output khác nhau cho cùng key do timestamp, random ID, thứ tự map hoặc môi trường ẩn, cache có thể che giấu sự không tái lập.

Để build có thể tái lập:

- Cố định compiler và plugin version.
- Đưa mọi compiler flag ảnh hưởng output vào key.
- Sắp xếp dữ liệu không có thứ tự theo quy tắc ổn định nếu ngữ nghĩa cho phép.
- Không chèn timestamp hoặc đường dẫn máy cục bộ tùy tiện.
- Cố định locale, timezone, encoding và newline khi ảnh hưởng output.
- Ghi nhận phiên bản dependency và schema.
- Bảo đảm code generation không dùng random hoặc clock ẩn.

Nếu cùng key có thể tạo hai artifact khác nhau, cần điều tra tính không xác định của compiler trước khi tin remote cache.

## 34. Cache trong môi trường nhiều tenant và nhiều workspace

Một dịch vụ compiler hoặc interpreter có thể phục vụ nhiều project. Cache dùng chung giúp tiết kiệm tài nguyên nhưng cần xác định ranh giới chia sẻ.

### Cache theo workspace

Token, AST và semantic model đang chỉnh sửa thường gắn với workspace hoặc document version. Chúng có thể không phù hợp để chia sẻ rộng nếu chứa path, source location hoặc trạng thái editor.

### Cache dùng chung theo nội dung

Artifact bất biến được tạo từ cùng source fingerprint, compiler và dependency có thể chia sẻ nếu không chứa dữ liệu riêng của workspace. Metadata đường dẫn và diagnostic có thể cần tách khỏi artifact dùng chung.

### Cache theo tenant

Execution result phụ thuộc dữ liệu tenant cần được phân vùng theo tenant hoặc security context. Không được dùng chung kết quả chỉ vì hai tenant có cùng khóa nghiệp vụ dạng chuỗi.

### Xóa và cô lập

Khi một workspace hoặc tenant bị xóa, cần xác định cache entry nào có thể xóa, entry nào là artifact công khai dùng chung và entry nào chứa dữ liệu riêng. Namespace và ownership rõ ràng giúp thực hiện chính sách này.

## 35. Cache và các chiến lược tối ưu khác

Cache chỉ là một công cụ tối ưu. Nó khác với một số kỹ thuật có vẻ tương tự.

| Kỹ thuật | Ý tưởng | Khác biệt với cache |
|---|---|---|
| Memoization | Lưu kết quả hàm theo đối số. | Là một dạng cache thường áp dụng cho hàm thuần. |
| Incremental computation | Chỉ tính lại phần bị ảnh hưởng. | Có thể không lưu kết quả lâu dài nhưng dùng dependency graph. |
| Common subexpression elimination | Tính một biểu thức chung một lần trong chương trình. | Là biến đổi compiler, không nhất thiết có cache runtime. |
| Constant folding | Tính trước biểu thức hằng lúc compile. | Kết quả được ghi vào IR/AST thay vì tra cache mỗi lần. |
| Precomputation | Tính trước kết quả trước khi có request. | Không nhất thiết được lập chỉ mục theo key động. |
| Lazy evaluation | Chỉ tính khi giá trị thực sự được dùng. | Điều khiển thời điểm tính, không tự động tái sử dụng giữa các lần. |
| Idempotency | Lặp thao tác có cùng hiệu ứng như một lần. | Là thuộc tính hành vi, không phải cơ chế cache. |

Một compiler có thể kết hợp nhiều kỹ thuật. Ví dụ, constant folding loại bỏ phép tính hằng, incremental compilation tránh build module không đổi, còn artifact cache chia sẻ output giữa các build.

## 36. Những sai lầm thường gặp

**Tạo key chỉ từ tên hoặc ID.** Cùng tên có thể trỏ đến nội dung, tenant hoặc version khác nhau. Key phải phản ánh đầu vào hiệu lực.

**Bỏ sót dependency.** Một schema hoặc module thay đổi nhưng cache vẫn được dùng vì fingerprint không bao gồm dependency đó.

**Cache hàm có tác dụng phụ.** Cache hit có thể bỏ qua gửi email, ghi database hoặc phát sự kiện mà mỗi lần gọi phải thực hiện.

**Coi TTL là bảo đảm correctness.** TTL chỉ giới hạn độ cũ; nó không bảo đảm kết quả luôn phản ánh dữ liệu mới nhất.

**Dùng chung kết quả giữa tenant hoặc người dùng.** Cache key thiếu security context có thể làm lộ dữ liệu hoặc trả kết quả sai quyền.

**Không version hóa artifact.** AST hoặc IR cũ có thể được deserialize bằng compiler không tương thích.

**Không xử lý cache stampede.** Nhiều request cùng miss có thể làm hệ thống quá tải vì cùng tính một kết quả đắt.

**Cache lỗi tạm thời quá lâu.** Timeout hoặc lỗi mạng có thể bị giữ như một kết quả không tìm thấy.

**Không phân biệt query plan và query result.** Plan có thể còn hợp lệ dù dữ liệu đổi; result có thể đã lỗi thời.

**Dùng object mutable trong cache chung.** Một request có thể làm thay đổi kết quả mà request khác đang sử dụng.

**Không gắn diagnostic với source version.** Lỗi cũ có thể được hiển thị sai vị trí sau khi tài liệu thay đổi.

**Đo hit rate mà không đo lợi ích.** Hit rate cao không đủ để chứng minh cache giảm latency hoặc chi phí.

**Dùng cache làm nguồn dữ liệu bền vững duy nhất.** Cache có thể bị eviction hoặc mất; dữ liệu nghiệp vụ cần lưu trữ bền vững phải có nguồn sự thật riêng.

## 37. Quy trình thiết kế bộ nhớ đệm kết quả

Một quy trình thực tế có thể gồm:

1. **Chọn phép xử lý:** xác định kết quả nào tốn kém và có khả năng được dùng lại.
2. **Xác định hợp đồng kết quả:** kiểu dữ liệu, trạng thái lỗi, tác dụng phụ và điều kiện tương đương.
3. **Liệt kê đầu vào hiệu lực:** đối số, source, compiler options, context, snapshot, quyền và môi trường.
4. **Xác định dependency:** ghi nhận module, schema, dữ liệu hoặc service có thể ảnh hưởng kết quả.
5. **Thiết kế cache key:** dùng fingerprint ổn định và không bỏ sót phụ thuộc.
6. **Chọn phạm vi cache:** theo request, execution, document, workspace, process, tenant hay remote service.
7. **Chọn invalidation:** version, dependency graph, event, TTL hoặc namespace epoch.
8. **Chọn eviction và giới hạn:** số entry, dung lượng, TTL và chính sách LRU/LFU phù hợp.
9. **Xử lý đồng thời:** single-flight, atomic write, lock hoặc cho phép compute trùng có kiểm soát.
10. **Xử lý lỗi và fallback:** phân biệt lỗi xác định, lỗi tạm thời, negative result và cache corruption.
11. **Bảo vệ dữ liệu:** tenant isolation, permission scope, integrity và retention.
12. **Đo lường:** hit/miss, latency, compute avoided, invalidation, eviction, memory và stale result.
13. **Kiểm thử:** thay đổi từng dependency, version, context, quyền, thời gian và trạng thái đồng thời.

## 38. Checklist cho một cache entry mới

Trước khi lưu một loại kết quả vào cache, hãy trả lời:

- Kết quả có xác định theo đầu vào được khai báo không?
- Phép tính có tác dụng phụ hoặc đọc trạng thái ẩn không?
- Đầu vào nào cần nằm trong cache key?
- Có dependency tĩnh hoặc động nào cần ghi nhận không?
- Cách phát hiện dependency thay đổi là gì?
- Entry thuộc phạm vi request, document, workspace, tenant hay toàn hệ thống?
- Có thể chia sẻ entry giữa người dùng hoặc project không?
- TTL có cần thiết không? Nếu có, giới hạn độ cũ nào được chấp nhận?
- Eviction được điều khiển theo số lượng hay dung lượng?
- Có cần negative caching không và thời gian lưu lỗi là bao lâu?
- Hai request cùng miss có được phép tính song song không?
- Nếu cache lỗi hoặc entry hỏng, fallback là gì?
- Kết quả có cần schema version hoặc checksum không?
- Diagnostic và source span có gắn với document version không?
- Dữ liệu nhạy cảm được bảo vệ và xóa theo chính sách nào?
- Metrics nào chứng minh cache thực sự có ích?

## 39. Kết quả cần có sau khi thiết kế cache

Một thiết kế bộ nhớ đệm kết quả hoàn chỉnh thường tạo ra:

- **Danh mục cache:** loại kết quả được lưu ở từng tầng compiler/interpreter.
- **Hợp đồng tính toán:** điều kiện purity, determinism, side effect và kết quả lỗi.
- **Cache key specification:** các input, version, option và fingerprint được đưa vào khóa.
- **Dependency model:** dependency graph, fingerprint và cách theo dõi thay đổi.
- **Invalidation policy:** quy tắc theo version, event, TTL hoặc namespace.
- **Storage policy:** in-process, local disk, shared hoặc remote cache; schema và integrity.
- **Capacity policy:** giới hạn dung lượng, TTL và eviction.
- **Concurrency policy:** xử lý cache stampede, atomic publication và lỗi tính toán.
- **Security policy:** tenant isolation, quyền truy cập, dữ liệu nhạy cảm và retention.
- **Observability:** hit/miss, latency, memory, invalidation, eviction và stale result.
- **Test plan:** kiểm tra correctness khi thay đổi source, dependency, context, phiên bản và môi trường.

Bộ nhớ đệm kết quả giúp compiler và interpreter tránh thực hiện lại những phép xử lý mà kết quả vẫn còn hợp lệ. Giá trị của cache phụ thuộc vào khả năng nhận diện chính xác đầu vào và phụ thuộc, chứ không chỉ vào tốc độ tra cứu. Khi cache key đầy đủ, invalidation đúng, trạng thái lỗi được phân loại, dữ liệu được cô lập theo quyền và các thao tác đồng thời được kiểm soát, hệ thống có thể tăng tốc biên dịch gia tăng và thực thi DSL mà vẫn giữ nguyên ngữ nghĩa. Nếu những điều kiện này không được bảo đảm, cache có thể biến một tối ưu hiệu năng thành nguồn gây lỗi khó tái hiện và khó giải thích.
