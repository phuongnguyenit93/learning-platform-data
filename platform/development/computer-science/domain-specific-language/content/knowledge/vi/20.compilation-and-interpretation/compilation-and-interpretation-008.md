# Biên dịch tăng dần

Trong một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), chương trình có thể gồm nhiều tệp, module, schema, quy tắc và tài nguyên. Khi người dùng sửa một phần nhỏ, việc biên dịch lại toàn bộ dự án có thể tốn thời gian dù phần lớn nội dung không thay đổi. **Biên dịch tăng dần** (*incremental compilation*) là kỹ thuật chỉ thực hiện lại những công việc bị ảnh hưởng bởi thay đổi, đồng thời tái sử dụng kết quả hợp lệ từ lần biên dịch trước.

Ví dụ, một dự án DSL triển khai hệ thống có các module `shared`, `billing`, `inventory` và `api`. Nếu người dùng chỉ đổi nội dung một thông điệp log trong `api`, compiler không nhất thiết phải phân tích kiểu và sinh mã lại cho toàn bộ `billing` hay `inventory`. Nếu người dùng đổi kiểu công khai `Money` trong `shared`, các module phụ thuộc vào kiểu đó có thể phải được kiểm tra lại.

Biên dịch tăng dần dựa trên ba ý tưởng chính:

1. Ghi nhận quan hệ phụ thuộc giữa các đơn vị chương trình.
2. Phát hiện chính xác phần đầu vào hoặc kết quả trung gian đã thay đổi.
3. Vô hiệu hóa và tính lại những kết quả có thể bị ảnh hưởng, giữ lại phần còn hợp lệ.

Mục tiêu là giảm thời gian phản hồi mà vẫn tạo ra kết quả tương đương với một lần biên dịch đầy đủ trên cùng trạng thái nguồn và cấu hình.

## 1. Biên dịch tăng dần là gì?

Một compiler truyền thống có thể thực hiện toàn bộ pipeline mỗi lần chạy:

```text
Source files
    |
    v
Lexing and parsing
    |
    v
Semantic analysis
    |
    v
Intermediate representation
    |
    v
Optimization
    |
    v
Code generation
    |
    v
Artifacts
```

Với dự án lớn, nhiều bước trong pipeline lặp lại dù đầu vào liên quan không thay đổi. Biên dịch tăng dần lưu lại kết quả của các bước trước và xác định phần nào cần chạy lại.

Ví dụ, nếu `models.dsl` định nghĩa kiểu `Customer`, còn `service.dsl` sử dụng kiểu đó, thay đổi nội dung một câu lệnh độc lập trong `service.dsl` có thể chỉ làm mất hiệu lực kết quả của tệp này. Nhưng nếu chữ ký công khai của `Customer` thay đổi, các tệp sử dụng kiểu đó cần được đánh giá lại.

### 1.1. Đơn vị tăng dần

Compiler có thể cập nhật theo nhiều đơn vị:

- **Tệp:** một tệp nguồn là đơn vị phân tích và cache.
- **Module:** nhiều tệp được gom thành một đơn vị có giao diện công khai.
- **Declaration:** chỉ một khai báo như kiểu, hàm hoặc rule được tính lại.
- **Biểu thức hoặc node:** một phần nhỏ trong AST hoặc IR được cập nhật.
- **Task:** một bước build như sinh schema, compile module hoặc đóng gói artifact.

Đơn vị càng nhỏ thì tiềm năng tiết kiệm càng lớn, nhưng việc theo dõi phụ thuộc và giữ kết quả nhất quán cũng phức tạp hơn. Một DSL vừa phải có thể bắt đầu ở mức tệp hoặc module; IDE có thể cần phân tích tăng dần đến mức declaration hoặc biểu thức.

### 1.2. Kết quả phải tương đương biên dịch đầy đủ

Tính đúng đắn quan trọng nhất là kết quả incremental phải phù hợp với kết quả nếu compiler chạy lại đầy đủ trên cùng nguồn, cấu hình và dependency.

Nếu một thay đổi ảnh hưởng đến một module nhưng compiler không phát hiện dependency, nó có thể tái sử dụng artifact cũ và tạo chương trình sai. Vì vậy, bỏ sót dependency nguy hiểm hơn việc tính lại dư một số đơn vị.

## 2. Vì sao cần biên dịch tăng dần?

Biên dịch tăng dần có ích khi chi phí phân tích hoặc sinh mã cao và mỗi lần chỉnh sửa chỉ ảnh hưởng một phần chương trình.

Những lợi ích thường gặp:

- **Phản hồi nhanh:** người dùng thấy lỗi cú pháp và kiểu sớm hơn trong IDE.
- **Tiết kiệm tài nguyên:** tránh lặp lại công việc phân tích và sinh mã không cần thiết.
- **Build nhanh hơn:** chỉ xây dựng lại module hoặc task bị ảnh hưởng.
- **Tăng năng suất:** vòng lặp sửa – chạy – kiểm tra ngắn hơn.
- **Hỗ trợ dự án lớn:** thời gian cập nhật có thể tỷ lệ với phạm vi thay đổi thay vì toàn bộ repository.

Ví dụ, một dự án có 300 module nhưng người dùng chỉ sửa một module lá. Nếu dependency graph cho thấy không có module nào khác phụ thuộc vào phần nội bộ vừa đổi, compiler có thể chỉ cần xử lý lại module đó và các artifact trực tiếp liên quan.

Tuy nhiên, incremental compilation không phải lúc nào cũng nhanh hơn. Với dự án rất nhỏ, chi phí theo dõi dependency, tính hash và quản lý cache có thể lớn hơn lợi ích. Một compiler có thể chọn full rebuild khi phạm vi thay đổi quá lớn hoặc trạng thái cache không đáng tin cậy.

## 3. Các khái niệm nền tảng

### 3.1. Đầu vào và kết quả trung gian

Mỗi giai đoạn compiler nhận một tập đầu vào và tạo kết quả. Ví dụ:

| Giai đoạn | Đầu vào | Kết quả |
|---|---|---|
| Lexing | Văn bản nguồn | Token stream |
| Parsing | Token stream | AST |
| Name resolution | AST, symbol index, imports | AST có symbol reference |
| Type checking | AST đã resolve, type environment | Thông tin kiểu và diagnostics |
| Lowering | AST hoặc typed AST | IR |
| Optimization | IR, target options | IR đã tối ưu |
| Code generation | IR, target configuration | Object code hoặc artifact |

Một kết quả trung gian có thể được tái sử dụng nếu mọi đầu vào có ảnh hưởng đến nó vẫn giữ nguyên.

### 3.2. Dependency

Một đơn vị phụ thuộc vào đơn vị khác nếu thay đổi ở đơn vị kia có thể làm kết quả của nó không còn hợp lệ.

Ví dụ:

```text
service.dsl uses billing.charge
billing.dsl defines billing.charge
```

Kết quả phân tích `service.dsl` phụ thuộc vào giao diện hoặc ngữ nghĩa liên quan của `billing.charge`.

### 3.3. Dirty và clean

Một đơn vị thường được gọi là:

- **Clean:** kết quả đã có và vẫn hợp lệ với các đầu vào hiện tại.
- **Dirty:** đầu vào hoặc dependency có thay đổi khiến kết quả cần được tính lại.

Dirty là trạng thái cần cập nhật, không nhất thiết có nghĩa bản thân văn bản của đơn vị đó đã được sửa. Một tệp không đổi vẫn có thể dirty vì kiểu mà nó sử dụng trong tệp khác vừa thay đổi.

### 3.4. Invalidation

**Invalidation** là việc đánh dấu một kết quả cache hoặc artifact không còn được phép sử dụng vì đầu vào liên quan đã thay đổi.

Ví dụ, khi chữ ký `charge(amount: Money)` đổi thành `charge(amount: Decimal)`, kết quả kiểm tra kiểu của các nơi gọi hàm có thể bị invalidated.

### 3.5. Cache key và fingerprint

Cache key xác định điều kiện để tái sử dụng kết quả. Nó có thể bao gồm hash nội dung, phiên bản compiler, tùy chọn, dependency fingerprint và target platform.

Fingerprint là dấu vân tay biểu diễn trạng thái của một đầu vào hoặc giao diện. Nếu fingerprint thay đổi, các kết quả phụ thuộc có thể cần tính lại.

## 4. Đồ thị phụ thuộc

Biên dịch tăng dần cần biết quan hệ giữa các đơn vị. Những quan hệ này thường được lưu thành **đồ thị phụ thuộc** (*dependency graph*).

Mỗi node biểu diễn một đơn vị như tệp, module, symbol hoặc task. Một cạnh biểu diễn rằng kết quả của một node phụ thuộc vào node khác.

Ví dụ:

```text
             shared-types
              /       \
             v         v
          billing   inventory
              \       /
               v     v
                 api
```

Trong sơ đồ, `billing`, `inventory` và `api` dùng các định nghĩa chung từ `shared-types`. `api` còn phụ thuộc kết quả của `billing` và `inventory`.

### 4.1. Quy ước hướng cạnh

Có hai cách biểu diễn phổ biến:

- Cạnh từ đơn vị sử dụng đến đơn vị được sử dụng: `api -> billing`.
- Cạnh từ đơn vị được sử dụng đến đơn vị sử dụng: `billing -> api`.

Cả hai đều có thể dùng được. Compiler phải chọn một quy ước nhất quán để duyệt đồ thị, tìm các đơn vị bị ảnh hưởng và tạo thứ tự build.

### 4.2. Dependency trực tiếp và bắc cầu

Nếu `A` phụ thuộc `B`, và `B` phụ thuộc `C`, thì `A` phụ thuộc gián tiếp vào `C`.

Khi `C` thay đổi, tác động có thể lan qua `B` đến `A`. Compiler cần xác định liệu thay đổi đó có ảnh hưởng đến giao diện mà `A` sử dụng hay không, thay vì luôn giả định mọi thay đổi của `C` đều buộc `A` phải compile lại.

### 4.3. Dependency ở các cấp khác nhau

Một compiler có thể lưu nhiều đồ thị:

- File dependency: tệp nào import tệp hoặc module nào.
- Symbol dependency: khai báo nào tham chiếu symbol nào.
- Type dependency: kết quả kiểu nào phụ thuộc vào định nghĩa kiểu nào.
- Task dependency: task build nào cần đầu ra của task khác.
- Artifact dependency: artifact nào được sinh từ những đầu vào nào.

Đồ thị chi tiết giúp giảm công việc thừa nhưng đòi hỏi cập nhật chính xác khi AST, symbol index hoặc cấu hình thay đổi.

## 5. Phát hiện đầu vào thay đổi

Trước khi quyết định tính lại, compiler cần xác định đầu vào có thay đổi hay không.

### 5.1. Timestamp

Một cách đơn giản là so sánh thời gian sửa đổi của tệp nguồn và artifact.

Nếu tệp nguồn mới hơn artifact, có thể đánh dấu task cần chạy lại.

Ưu điểm:

- Dễ triển khai.
- Không cần đọc và hash toàn bộ nội dung khi timestamp đáng tin cậy.
- Phù hợp với một số workflow build truyền thống.

Hạn chế:

- Timestamp có thể không chính xác hoặc có độ phân giải thấp.
- Sao chép tệp có thể giữ timestamp cũ.
- Đồng hồ hệ thống có thể lệch.
- Một số công cụ tạo lại tệp với nội dung giống hệt nhưng timestamp mới.

Timestamp hữu ích như một tín hiệu nhanh, nhưng với cache cần độ tin cậy cao, thường nên kết hợp với nội dung hoặc fingerprint.

### 5.2. Hash nội dung

Compiler có thể tính hash từ byte hoặc nội dung chuẩn hóa của tệp. Nếu hash không đổi, có thể xem nội dung nguồn không đổi theo mô hình hash được dùng.

Ví dụ:

```text
hash(models.dsl) = H1
```

Sau khi người dùng sửa tệp:

```text
hash(models.dsl) = H2
```

Nếu `H1 != H2`, nội dung đã thay đổi và các kết quả phụ thuộc cần được xem xét.

Hash nội dung thường đáng tin cậy hơn timestamp cho việc phát hiện thay đổi, nhưng cần đọc nội dung để tính hash. Với tệp lớn, compiler có thể kết hợp timestamp để tránh tính hash khi không cần.

### 5.3. Hash đầu vào đầy đủ của task

Một task không chỉ phụ thuộc vào một tệp. Kết quả có thể phụ thuộc vào:

- Tất cả tệp nguồn liên quan.
- Phiên bản compiler và plugin.
- Cờ biên dịch.
- Phiên bản grammar hoặc schema.
- Target architecture và runtime.
- Environment variables được khai báo là đầu vào.
- Dependency artifact và API fingerprint.

Cache key cần phản ánh mọi yếu tố có thể làm thay đổi kết quả. Nếu bỏ sót một đầu vào, compiler có thể dùng artifact cũ trong khi kết quả đúng đã thay đổi.

### 5.4. Chuẩn hóa trước khi hash

Trong một số trường hợp, compiler có thể hash biểu diễn chuẩn hóa thay vì văn bản thô. Ví dụ, thay đổi khoảng trắng hoặc comment có thể không làm thay đổi AST và ngữ nghĩa.

Tuy nhiên, chuẩn hóa chỉ an toàn nếu compiler xác định chính xác phần nào không ảnh hưởng kết quả. Với DSL nhạy thụt lề, khoảng trắng có thể mang ý nghĩa. Với macro hoặc source map, vị trí nguồn và comment có thể ảnh hưởng tooling dù không đổi ngữ nghĩa runtime.

## 6. Phân biệt thay đổi nội bộ và thay đổi giao diện

Một trong những cách quan trọng để giảm biên dịch lại là phân biệt thay đổi phần triển khai nội bộ với thay đổi giao diện mà module khác sử dụng.

Ví dụ:

```text
module billing {
    public function total(items: List<Item>): Money
    private function applyDiscount(...)
}
```

Nếu chỉ sửa phần thân `applyDiscount` mà chữ ký và hợp đồng công khai không đổi, module tiêu thụ có thể không cần kiểm tra kiểu lại.

Nếu đổi chữ ký public:

```text
total(items: List<Item>, taxRate: Decimal): Money
```

thì các nơi gọi `total` có thể bị ảnh hưởng.

### 6.1. API fingerprint

Compiler có thể tạo fingerprint từ phần giao diện công khai của module, gồm:

- Tên và loại symbol được export.
- Chữ ký hàm và phương thức.
- Kiểu dữ liệu và generic constraints.
- Quan hệ kế thừa hoặc interface công khai.
- Visibility và metadata ảnh hưởng đến người sử dụng.
- Các bất biến hoặc contract mà compiler đưa vào ngữ nghĩa API.

Nếu phần triển khai nội bộ thay đổi nhưng API fingerprint giữ nguyên, một số kết quả của module phụ thuộc có thể được tái sử dụng.

### 6.2. Thay đổi thân hàm

Thay đổi thân hàm có thể không làm thay đổi type checking ở nơi gọi, nhưng vẫn có thể ảnh hưởng đến:

- Code generation của module chứa hàm.
- Inline expansion nếu compiler inline hàm.
- Constant evaluation nếu hàm được dùng tại compile time.
- Macro hoặc template phụ thuộc nội dung hàm.
- Kiểm tra hiệu ứng hoặc contract nếu chúng được suy ra từ phần thân.

Vì vậy, “API không đổi” chỉ cho phép giữ lại những kết quả mà thật sự chỉ phụ thuộc API. Artifact cuối cùng của module chứa phần thân thay đổi vẫn cần được sinh lại.

### 6.3. Thay đổi private nhưng ảnh hưởng public

Một hàm private có thể được dùng để tính giá trị mặc định công khai hoặc tạo metadata export. Nếu thay đổi của nó làm thay đổi kết quả công khai, API fingerprint hoặc một fingerprint ngữ nghĩa liên quan cũng cần thay đổi.

Không nên quyết định dựa vào từ khóa `private` một cách máy móc; phải xét quan hệ phụ thuộc thực tế.

## 7. Invalidation và lan truyền thay đổi

Khi một đầu vào thay đổi, compiler cần xác định các kết quả có thể bị ảnh hưởng. Quá trình này gọi là invalidation.

Giả sử đồ thị có hướng theo quy ước “node sử dụng trỏ đến dependency”:

```text
api -> billing
api -> inventory
billing -> shared
inventory -> shared
```

Nếu `shared` thay đổi, các node phụ thuộc trực tiếp hoặc gián tiếp có thể cần được xem xét: `billing`, `inventory` và `api`.

### 7.1. Tính tập ảnh hưởng

Compiler có thể duyệt ngược đồ thị dependency để tìm tất cả consumer của một node thay đổi. Nếu đồ thị lưu chiều ngược, việc tìm consumer có thể là duyệt theo các cạnh đi ra.

Không phải mọi consumer đều phải chạy lại mọi bước. Có thể chỉ một phần kết quả của chúng bị invalidated, tùy loại thay đổi và loại dependency.

### 7.2. Invalidation bảo thủ

Nếu compiler không chắc một thay đổi có ảnh hưởng hay không, nó có thể đánh dấu nhiều đơn vị hơn cần chạy lại. Cách này giảm nguy cơ dùng kết quả sai nhưng có thể làm build chậm.

### 7.3. Invalidation chính xác

Nếu compiler theo dõi dependency đến symbol hoặc interface fingerprint, nó có thể giữ lại nhiều kết quả hơn. Cách này nhanh hơn nhưng đòi hỏi mô hình dependency đầy đủ và cập nhật đúng.

### 7.4. Thay đổi lan truyền

Một thay đổi có thể lan qua nhiều tầng:

```text
Change in shared type
        |
        v
Recheck billing and inventory
        |
        v
Update their exported fingerprints
        |
        v
Recheck api if a consumed interface changed
        |
        v
Regenerate affected artifacts
```

Nếu fingerprint của một dependency không đổi, lan truyền có thể dừng ở đó cho những bước chỉ phụ thuộc giao diện.

## 8. Cache trong biên dịch tăng dần

Cache lưu kết quả đã tính để tái sử dụng. Một compiler có thể cache token stream, AST, symbol index, type result, IR, object code hoặc artifact cuối.

### 8.1. Cache theo giai đoạn

| Cache | Có thể tái sử dụng khi |
|---|---|
| Token stream | Nội dung và cấu hình lexer liên quan không đổi |
| AST | Token/nguồn và phiên bản grammar không đổi |
| Symbol index | Tập khai báo và quy tắc namespace liên quan không đổi |
| Typed AST | AST cùng các symbol/type dependency không đổi |
| IR | Typed AST và cấu hình lowering không đổi |
| Optimized IR | IR và tùy chọn optimizer không đổi |
| Object code | IR, backend, target và cờ sinh mã không đổi |
| Artifact đóng gói | Các artifact đầu vào và cấu hình package không đổi |

### 8.2. Cache key

Một cache key cần kết hợp những đầu vào quyết định kết quả. Ví dụ khái niệm:

```text
cacheKey = hash(
    sourceContent,
    compilerVersion,
    grammarVersion,
    compileOptions,
    targetPlatform,
    dependencyFingerprints
)
```

Nếu `compileOptions` thay đổi từ tối ưu hóa mức 1 sang mức 2, object code có thể khác dù nguồn không đổi. Vì vậy, không thể chỉ dùng hash tệp nguồn làm cache key cho mọi giai đoạn.

### 8.3. Cache cục bộ và cache từ xa

- **Local cache:** lưu trên máy phát triển hoặc máy build hiện tại, giúp các lần chạy tiếp theo nhanh hơn.
- **Remote cache:** lưu artifact theo cache key ở một nơi dùng chung, cho phép máy khác tái sử dụng kết quả đã tạo.

Remote cache hữu ích trong CI hoặc nhóm nhiều người, nhưng cần đảm bảo artifact gắn với đúng cache key và được kiểm tra nguồn gốc. Không nên tin artifact chỉ vì nó có tên tệp giống với đầu ra mong muốn.

### 8.4. Cache hit và cache miss

- **Cache hit:** tìm được kết quả tương ứng với cache key hiện tại và kết quả được xác minh hợp lệ.
- **Cache miss:** không có kết quả phù hợp; task phải chạy lại.

Một hệ thống có thể ghi log lý do cache miss như source changed, compiler changed, dependency fingerprint changed hoặc output missing. Thông tin này giúp người phát triển hiểu vì sao build vẫn phải chạy.

### 8.5. Cache không phải nguồn sự thật duy nhất

Cache là bản sao của kết quả có thể tái tạo. Nếu cache bị thiếu, hỏng hoặc không đáng tin, compiler phải có khả năng tính lại từ đầu. Xóa cache có thể làm build chậm hơn nhưng không được làm thay đổi ngữ nghĩa chương trình.

## 9. Build graph và thứ tự thực thi

Biên dịch tăng dần thường được phối hợp với một build system quản lý task graph.

Ví dụ:

```text
compile-shared
      |
      +-------> compile-billing -----+
      |                             |
      +-------> compile-inventory --+--> compile-api --> package
```

Mỗi task khai báo đầu vào, đầu ra và dependency. Build system có thể:

1. Kiểm tra đầu vào và cache key của từng task.
2. Bỏ qua task có đầu ra hợp lệ.
3. Đưa task cần chạy vào hàng đợi.
4. Chỉ chạy task sau khi dependency của nó hoàn tất.
5. Chạy song song những task độc lập.
6. Ghi lại artifact và metadata để lần sau tái sử dụng.

### 9.1. Task graph khác dependency graph ngữ nghĩa

Dependency graph ngữ nghĩa mô tả quan hệ giữa symbol, kiểu hoặc module trong DSL. Build graph mô tả quan hệ giữa các công việc tạo artifact.

Hai đồ thị liên quan nhưng không nhất thiết giống nhau. Một module có thể cần nhiều task như generate schema, compile source, package resource. Một task có thể phụ thuộc vào tệp cấu hình không phải mã DSL.

### 9.2. Thứ tự topo

Nếu build graph không có chu trình, build system có thể tạo thứ tự topo để task đầu vào hoàn tất trước task sử dụng đầu ra đó.

### 9.3. Task không khai báo đủ dependency

Nếu task đọc một tệp nhưng không khai báo tệp đó là input, build system có thể không biết khi nào cần chạy lại. Đây là lỗi cấu hình nguy hiểm vì build incremental có thể báo thành công nhưng artifact cũ vẫn được dùng.

## 10. Biên dịch tăng dần trong DSL nhiều tệp

Xét một project DSL:

```text
shop/
├── shared/types.dsl
├── billing/invoice.dsl
├── inventory/stock.dsl
└── api/checkout.dsl
```

Nội dung phụ thuộc:

```text
# shared/types.dsl
public type Money = Decimal
public type ProductId = String
```

```text
# billing/invoice.dsl
import shared.Money

public function calculateTotal(items: List<Item>): Money
```

```text
# inventory/stock.dsl
import shared.ProductId

public function available(id: ProductId): Boolean
```

```text
# api/checkout.dsl
import billing.calculateTotal
import inventory.available
```

### 10.1. Thay đổi nội bộ ở checkout

Nếu chỉ sửa một thông điệp log trong `checkout.dsl`, compiler cần parse và compile lại phần bị ảnh hưởng trong module `api`. Nếu log không ảnh hưởng API được export, `billing` và `inventory` có thể giữ nguyên.

### 10.2. Thay đổi giao diện Money

Nếu `Money` đổi từ alias `Decimal` thành kiểu danh nghĩa có quy tắc riêng, `billing.calculateTotal` có thể cần type check lại. Các nơi gọi hàm này trong `api` có thể cũng cần kiểm tra lại nếu fingerprint giao diện của hàm thay đổi.

`inventory` không sử dụng `Money`, nên có thể không cần chạy lại.

### 10.3. Thay đổi compiler option

Nếu đổi target từ runtime A sang runtime B, các bước sinh mã có thể cần chạy lại ngay cả khi source và AST không đổi. Một số cache ở giai đoạn parse hoặc semantic analysis vẫn có thể dùng lại nếu target không ảnh hưởng chúng.

### 10.4. Thay đổi dependency version

Nếu phiên bản module `shared` thay đổi, analyzer cần resolve lại dependency và so sánh API fingerprint. Nếu giao diện không đổi, một số module tiêu thụ có thể giữ lại semantic result; nếu API thay đổi, consumer liên quan phải được invalidated.

## 11. Biên dịch tăng dần và macro, template, code generation

DSL có thể hỗ trợ macro, template hoặc sinh mã từ schema. Những cơ chế này làm dependency phức tạp hơn vì đầu ra có thể phụ thuộc vào nhiều nguồn.

Ví dụ:

```text
generateClient from schema "api.schema"
using template "client.template"
target "typescript"
```

Artifact client phụ thuộc vào:

- Nội dung `api.schema`.
- Nội dung template.
- Phiên bản generator.
- Tùy chọn target TypeScript.
- Các dependency mà schema tham chiếu.

Nếu chỉ hash schema mà bỏ qua template hoặc generator version, compiler có thể dùng client code cũ dù template đã thay đổi.

### 11.1. Macro expansion

Macro có thể mở rộng thành AST hoặc token. Kết quả expansion phụ thuộc định nghĩa macro, tham số, môi trường và có thể cả vị trí gọi. Khi macro definition thay đổi, mọi nơi dùng macro có thể cần được phân tích lại.

### 11.2. Template generation

Template sinh mã thường phụ thuộc dữ liệu mô hình và template file. Compiler cần theo dõi cả hai loại đầu vào, đồng thời lưu source map hoặc origin metadata nếu cần truy vết lỗi về DSL.

### 11.3. Generated source

Nếu mã sinh ra lại được đưa vào pipeline compile, cần xác định artifact đó là đầu vào dẫn xuất. Không nên coi nó như nguồn độc lập không có quan hệ với generator, nếu không invalidation có thể bỏ sót thay đổi ở nguồn gốc.

## 12. Tính đúng đắn và tính xác định

Incremental compilation chỉ có ích nếu kết quả đúng. Một nguyên tắc quan trọng là mọi đầu vào có ảnh hưởng phải được khai báo hoặc phát hiện.

### 12.1. Không bỏ sót dependency

Nếu task đọc một file cấu hình, environment variable hoặc resource ngoài nhưng không ghi nhận dependency, thay đổi ở đó có thể không kích hoạt rebuild.

### 12.2. Không dùng cache của cấu hình khác

Cache phải phân biệt các tùy chọn ảnh hưởng kết quả, chẳng hạn:

- Phiên bản compiler.
- Phiên bản plugin.
- Target platform.
- Cờ tối ưu hóa.
- Feature flag.
- Phiên bản schema hoặc dependency.
- Encoding và tùy chọn parser nếu chúng ảnh hưởng kết quả.

### 12.3. Tính xác định của compiler

Nếu compiler phụ thuộc vào thời gian hiện tại, thứ tự duyệt tệp không ổn định hoặc dữ liệu mạng thay đổi, cùng đầu vào có thể tạo kết quả khác nhau. Điều này làm cache khó tin cậy.

Compiler nên tránh phụ thuộc ngầm vào môi trường. Những đầu vào ngoài cần thiết phải được khai báo, cố định hoặc đưa vào cache key.

### 12.4. Kiểm tra incremental so với full build

Một cách kiểm chứng ở cấp hệ thống là so sánh artifact hoặc kết quả semantic của incremental build với full build trên cùng snapshot. Đây là chiến lược xác nhận tính tương đương của cơ chế build; việc kiểm thử chi tiết thuộc quy trình kiểm tra riêng của dự án.

## 13. Thay đổi xóa, đổi tên và di chuyển

Theo dõi thay đổi không chỉ gồm nội dung tệp được sửa. Compiler cần xử lý cả việc xóa, đổi tên và di chuyển nguồn.

### 13.1. Xóa tệp

Nếu một tệp bị xóa, các symbol nó cung cấp không còn tồn tại. Những consumer tham chiếu đến symbol đó cần được phân tích lại và có thể phát lỗi unresolved reference.

### 13.2. Đổi tên tệp

Nếu đường dẫn là một phần của module identity hoặc source mapping, đổi tên tệp có thể thay đổi danh tính nguồn. Nếu namespace không phụ thuộc đường dẫn, việc đổi tên có thể chỉ làm thay đổi metadata và vị trí diagnostic.

### 13.3. Di chuyển tệp

Compiler cần phân biệt di chuyển cùng nội dung với xóa tệp cũ và thêm tệp mới. Cache có thể tái sử dụng AST nếu nội dung và điều kiện liên quan không đổi, nhưng source span và URI cần được cập nhật.

### 13.4. Đổi tên symbol

Đổi tên symbol ảnh hưởng các tham chiếu đã resolve đến symbol đó. Nếu analyzer có symbol identity và reference index, nó có thể tìm chính xác consumer thay vì tìm kiếm chuỗi tên trên toàn project.

## 14. Phân tích tăng dần trong IDE

IDE cần phản hồi ngay khi người dùng gõ, vì vậy incremental analysis thường hoạt động ở mức nhỏ hơn build thông thường.

Một Language Server có thể duy trì:

- Nội dung và version của các tài liệu đang mở.
- Token stream và AST của từng tệp.
- Symbol index và dependency graph.
- Kết quả phân giải tên và kiểm tra kiểu.
- Diagnostics theo document version.
- Cache của các biểu thức hoặc declaration không thay đổi.

### 14.1. Sửa một biểu thức

Nếu người dùng sửa một literal trong hàm, parser có thể chỉ cần cập nhật vùng AST liên quan. Semantic analyzer kiểm tra lại node và các biểu thức phụ thuộc.

### 14.2. Sửa chữ ký công khai

Nếu người dùng đổi kiểu tham số của hàm công khai, analyzer cần tìm các call site đã resolve đến hàm đó. Những nơi gọi có thể phải được type check lại.

### 14.3. Tài liệu chưa lưu

IDE thường phân tích nội dung mới trong bộ nhớ, không chỉ nội dung trên đĩa. Khi nhiều tệp đang mở và chưa lưu, workspace snapshot cần kết hợp đúng phiên bản hiện tại của từng tài liệu.

### 14.4. Hủy tác vụ cũ

Người dùng có thể gõ tiếp khi một lần phân tích đang chạy. IDE có thể hủy hoặc bỏ qua kết quả cũ nếu version đã lỗi thời, rồi ưu tiên phân tích snapshot mới nhất.

### 14.5. Phân tích gần đúng khi tệp chưa hoàn chỉnh

Trong lúc gõ, mã nguồn có thể tạm thời không hợp cú pháp. Parser phục hồi có thể tạo AST một phần để IDE vẫn cung cấp completion và diagnostics cho vùng còn hiểu được.

## 15. Biên dịch tăng dần và thực thi song song

Khi dependency graph đã xác định, các đơn vị độc lập có thể được xử lý song song.

Ví dụ:

```text
           shared
          /      \
         v        v
      billing  inventory
          \      /
           v    v
             api
```

Sau khi `shared` hoàn tất, `billing` và `inventory` có thể được compile song song nếu không có dependency bổ sung giữa chúng. `api` chỉ chạy sau khi các đầu ra cần thiết đã sẵn sàng.

### 15.1. Lợi ích

- Tận dụng nhiều core CPU.
- Giảm thời gian build cho graph có nhiều nhánh độc lập.
- Có thể kết hợp với remote cache và task scheduling.

### 15.2. Điều kiện

- Dependency graph phải đầy đủ.
- Task không được ghi đè đầu ra của nhau ngoài quy tắc đã định.
- Cache và artifact phải an toàn khi truy cập đồng thời.
- Thứ tự publish hoặc commit output phải được kiểm soát.
- Lỗi ở một task cần được truyền đến task phụ thuộc theo chính sách.

### 15.3. Race condition trong cache

Hai worker có thể cùng yêu cầu một cache key. Hệ thống nên tránh việc cả hai ghi artifact không hoàn chỉnh hoặc một worker đọc file khi worker khác đang ghi.

Một cách triển khai là ghi vào tệp tạm, xác minh thành công rồi đổi tên nguyên tử vào vị trí cache. Lock hoặc cơ chế content-addressed storage cũng có thể được dùng tùy kiến trúc.

## 16. Biên dịch tăng dần và trạng thái lỗi

Khi một đơn vị compile thất bại, compiler cần quản lý artifact cũ của đơn vị đó và các consumer.

### 16.1. Không dùng artifact cũ như thể vừa build thành công

Nếu `billing` thay đổi nhưng compile thất bại, artifact `billing` cũ có thể vẫn tồn tại trên đĩa. Build system không được âm thầm đóng gói artifact cũ như kết quả của source mới, trừ khi chế độ cụ thể cho phép dùng bản gần nhất và hiển thị rõ trạng thái.

### 16.2. Giữ kết quả thành công độc lập

Một module không liên quan có thể compile thành công và giữ artifact mới ngay cả khi module khác lỗi. Tuy nhiên, artifact cuối của toàn project chỉ nên được công bố khi các điều kiện build được thỏa mãn.

### 16.3. Diagnostic cũ

Khi một tệp được sửa và phân tích lại, diagnostics cũ của version trước cần được thay thế hoặc xóa. Nếu không, IDE có thể hiển thị lỗi đã được sửa.

### 16.4. Lỗi dependency

Nếu module nền tảng không compile được, các module phụ thuộc có thể không đủ thông tin để tiếp tục. Compiler có thể dừng nhánh đó và vẫn phân tích các nhánh độc lập để đưa ra nhiều thông tin hữu ích.

## 17. Thiết kế cache an toàn

Cache có thể nằm trên máy local hoặc máy chủ dùng chung. Một số nguyên tắc giúp tránh dùng kết quả sai:

- Cache key phải bao gồm mọi đầu vào có ảnh hưởng.
- Artifact nên được ghi nguyên tử sau khi task thành công.
- Metadata cache cần lưu phiên bản compiler và dependency.
- Không tái sử dụng artifact không xác định được nguồn gốc.
- Có thể kiểm tra checksum để phát hiện hỏng dữ liệu.
- Có chính sách hết hạn hoặc dọn cache để quản lý dung lượng.
- Cache miss phải dẫn đến tính lại, không làm thay đổi ngữ nghĩa.

### 17.1. Content-addressed storage

Một số hệ thống đặt tên artifact theo hash nội dung hoặc cache key. Nhờ vậy, cùng một đầu vào có thể tham chiếu đến cùng một artifact, và nhiều project có thể chia sẻ kết quả nếu toàn bộ điều kiện tương ứng giống nhau.

### 17.2. Remote cache và độ tin cậy

Remote cache giúp nhiều máy dùng chung artifact, nhưng cần kiểm soát quyền ghi, quyền đọc và tính toàn vẹn. Nếu artifact bị thay thế bởi nội dung không tương ứng với cache key, build có thể tạo kết quả sai hoặc không an toàn.

### 17.3. Cache eviction

Cache eviction xóa những entry ít được dùng hoặc đã cũ để giải phóng dung lượng. Vì cache có thể tái tạo, eviction không được làm mất nguồn dữ liệu duy nhất của project.

## 18. Các mức độ tăng dần

Không phải compiler nào cũng có cùng mức granular. Có thể phân loại khái quát:

| Mức | Đơn vị cập nhật | Đặc điểm |
|---|---|---|
| Build theo tệp | Tệp nguồn | Đơn giản, phù hợp dự án nhỏ hoặc module độc lập |
| Build theo module | Module | Dựa vào giao diện module và dependency |
| Build theo task | Task/artifact | Tích hợp với build system, hỗ trợ cache và song song |
| Semantic incremental | Symbol/declaration | Theo dõi tham chiếu và API fingerprint |
| IDE incremental | Node hoặc vùng tài liệu | Phản hồi nhanh khi người dùng chỉnh sửa |

Các mức này có thể cùng tồn tại. Một IDE có thể phân tích tăng dần theo node, trong khi build phát hành vẫn đóng gói theo module.

## 19. So sánh biên dịch đầy đủ và biên dịch tăng dần

| Tiêu chí | Full compilation | Incremental compilation |
|---|---|---|
| Phạm vi | Tính lại toàn bộ pipeline hoặc phần lớn project | Chỉ tính lại phần bị ảnh hưởng |
| Thời gian khi thay đổi nhỏ | Có thể tốn nhiều thời gian | Thường nhanh hơn nếu dependency được theo dõi tốt |
| Độ phức tạp triển khai | Tương đối đơn giản | Cao hơn do dependency, cache và invalidation |
| Rủi ro cache lỗi thời | Ít hơn nếu luôn tính lại | Cần kiểm soát chặt đầu vào và cache key |
| Tính nhất quán | Dễ xác định theo một snapshot nguồn | Phải quản lý snapshot và trạng thái từng đơn vị |
| Sử dụng tài nguyên | Có thể lặp công việc lớn | Có thể tiết kiệm CPU và I/O |
| Phù hợp | Dự án nhỏ, build sạch, kiểm tra đối chiếu | Dự án lớn, IDE, vòng lặp phát triển thường xuyên |

Full compilation vẫn hữu ích làm đường cơ sở, chế độ build sạch và cách khôi phục khi cache hoặc dependency metadata không đáng tin.

## 20. Ví dụ quy trình incremental compilation

Giả sử project có các module:

```text
core-types
    |
    +----> payments ----+
    |                  |
    +----> orders ------+----> storefront
```

Mỗi module có một API fingerprint và artifact riêng.

### 20.1. Lần build đầu tiên

Ở lần đầu, chưa có cache hợp lệ. Compiler cần:

1. Parse và kiểm tra `core-types`.
2. Tạo API fingerprint và artifact của `core-types`.
3. Compile `payments` và `orders` dựa trên giao diện của `core-types`.
4. Compile `storefront` dựa trên giao diện của `payments` và `orders`.
5. Lưu cache key, fingerprint và artifact cho từng đơn vị.

### 20.2. Sửa nội dung nội bộ của orders

Người dùng thay đổi thuật toán bên trong một hàm private trong `orders` nhưng không thay đổi API công khai.

Compiler có thể:

1. Phát hiện hash nội dung `orders` thay đổi.
2. Parse và compile lại `orders`.
3. Tính lại API fingerprint.
4. So sánh fingerprint mới với fingerprint cũ.
5. Nếu fingerprint không đổi, giữ lại kết quả semantic của `storefront` phụ thuộc API đó.
6. Tạo artifact mới cho `orders` và đóng gói phần bị ảnh hưởng.

### 20.3. Đổi chữ ký hàm public

Nếu `orders.createOrder` đổi tham số hoặc kiểu trả về, API fingerprint thay đổi. Khi đó `storefront` cần được kiểm tra lại vì có thể đang gọi hàm theo chữ ký cũ.

`payments` không nhất thiết phải chạy lại nếu nó không phụ thuộc symbol hoặc metadata bị thay đổi.

### 20.4. Thay compiler version

Nếu compiler version thay đổi, cache key của những giai đoạn phụ thuộc phiên bản compiler có thể không còn hợp lệ. Một số cache nguồn hoặc token có thể vẫn dùng lại nếu định dạng và ngữ nghĩa tương thích, nhưng quyết định này phải do compiler quy định.

## 21. Các yếu tố đặc biệt ảnh hưởng incremental build

### 21.1. Environment variables

Nếu compiler đọc biến môi trường để chọn target hoặc feature, giá trị đó phải được coi là đầu vào. Nếu không, thay đổi môi trường có thể không kích hoạt build lại.

### 21.2. File được sinh tự động

Generated file cần có quan hệ nguồn gốc với generator và đầu vào của nó. Khi schema thay đổi, generated file và consumer của nó có thể cần được cập nhật.

### 21.3. Plugin và compiler extension

Plugin có thể thêm grammar, rule hoặc code generation. Cache key cần tính đến phiên bản plugin và cấu hình plugin nếu chúng ảnh hưởng kết quả.

### 21.4. Thời gian và dữ liệu mạng

Một bước build đọc thời gian hiện tại hoặc truy vấn API từ xa có thể tạo kết quả không xác định. Muốn cache đáng tin, cần cố định dữ liệu đầu vào, ghi nhận snapshot hoặc đánh dấu task không thể cache an toàn.

### 21.5. Tệp cấu hình và lockfile

Thay đổi project configuration, dependency lockfile hoặc target settings có thể ảnh hưởng nhiều task dù source không đổi. Những tệp này phải được đưa vào dependency graph.

## 22. Quan sát và chẩn đoán incremental build

Khi build không chạy như mong đợi, người phát triển cần biết task nào được chạy, task nào được bỏ qua và lý do.

Một log hữu ích có thể hiển thị:

```text
[UP-TO-DATE] compile:core-types
[EXECUTED]   compile:orders (source content changed)
[UP-TO-DATE] compile:payments (inputs unchanged)
[EXECUTED]   compile:storefront (orders API fingerprint changed)
[FROM-CACHE] package:assets
```

Những thông tin hữu ích gồm:

- Cache hit hoặc miss.
- Đầu vào nào thay đổi.
- Dependency fingerprint nào thay đổi.
- Task nào bị invalidated.
- Lý do task phải chạy lại.
- Thời gian của từng giai đoạn.
- Artifact được tạo ở đâu và từ cache key nào.

Thông tin này giúp phân biệt build chậm do dependency graph quá rộng, cache miss thường xuyên hay một task vốn phải chạy lại.

## 23. Những sai lầm thường gặp

**Chỉ so sánh timestamp.** Timestamp có thể không phản ánh chính xác nội dung; nên dùng fingerprint hoặc cơ chế xác minh phù hợp.

**Chỉ hash tệp nguồn.** Kết quả còn phụ thuộc compiler version, option, target, plugin và dependency.

**Không ghi nhận dependency ẩn.** Một task đọc tệp hoặc environment variable nhưng không khai báo input có thể giữ artifact lỗi thời.

**Invalidation quá rộng.** Mọi thay đổi đều làm build lại toàn project sẽ làm mất phần lớn lợi ích incremental.

**Invalidation quá hẹp.** Bỏ sót consumer của một API thay đổi có thể khiến compiler dùng kết quả không còn hợp lệ.

**Nhầm thay đổi nội bộ với thay đổi API.** Có thể giữ lại một số kết quả semantic của consumer nếu giao diện không đổi, nhưng artifact của module có thân hàm thay đổi vẫn cần cập nhật.

**Tái sử dụng artifact sau khi compile thất bại.** Artifact cũ không được trình bày như kết quả của source mới nếu chưa được xác nhận hợp lệ.

**Không quản lý version của tài liệu IDE.** Kết quả phân tích cũ có thể được áp dụng lên nội dung mới và hiển thị diagnostics sai.

**Không có full rebuild để đối chiếu.** Khi cache hoặc dependency tracking gặp vấn đề, cần có cách tạo lại kết quả từ đầu để khôi phục và so sánh.

## 24. Ghi nhớ

- Biên dịch tăng dần chỉ tính lại những phần bị ảnh hưởng và tái sử dụng kết quả còn hợp lệ.
- Dependency graph cho biết thay đổi ở một đơn vị có thể ảnh hưởng đến đơn vị nào.
- Dirty, clean và invalidation mô tả trạng thái hợp lệ của kết quả trung gian.
- Timestamp, hash nội dung và fingerprint giúp phát hiện thay đổi; cache key phải bao gồm mọi đầu vào ảnh hưởng kết quả.
- Phân biệt thay đổi nội bộ với thay đổi API giúp giảm việc biên dịch lại consumer.
- Invalidation cần đủ bảo thủ để không bỏ sót dependency, nhưng đủ chính xác để tránh tính lại không cần thiết.
- Cache có thể lưu AST, symbol index, typed AST, IR, object code và artifact; mỗi loại cần điều kiện tái sử dụng riêng.
- Build graph điều phối task, thứ tự topo, cache và thực thi song song.
- Macro, template, plugin, generated source và environment variables cũng có thể là dependency.
- IDE cần snapshot và document version để kết quả incremental không bị lỗi thời.
- Full build vẫn hữu ích làm chế độ sạch, khôi phục và cơ sở đối chiếu.

## 25. Câu hỏi tự kiểm tra

1. Biên dịch tăng dần là gì và nó giải quyết vấn đề nào trong dự án DSL lớn?
2. Phân biệt dependency graph ngữ nghĩa với build task graph.
3. Vì sao một tệp không thay đổi vẫn có thể bị đánh dấu dirty?
4. Invalidation là gì? Hãy nêu ví dụ khi kiểu công khai thay đổi.
5. Timestamp và hash nội dung có ưu điểm, hạn chế nào khi phát hiện thay đổi?
6. Cache key cần bao gồm những loại đầu vào nào ngoài nội dung tệp nguồn?
7. API fingerprint giúp phân biệt thay đổi nội bộ với thay đổi giao diện như thế nào?
8. Vì sao thay đổi thân một hàm private vẫn có thể yêu cầu sinh mã lại cho module chứa nó?
9. Hãy mô tả cách thay đổi ở một module nền tảng lan truyền qua dependency graph.
10. Cache hit và cache miss có ý nghĩa gì? Vì sao cache không nên là nguồn sự thật duy nhất?
11. Tại sao một task đọc environment variable hoặc template phải khai báo dependency tương ứng?
12. Incremental analysis trong IDE cần quản lý document version và workspace snapshot ra sao?
13. Khi hai task độc lập cùng cần chạy, build system có thể thực thi song song với những điều kiện nào?
14. Vì sao cần có khả năng full rebuild để khôi phục hoặc đối chiếu kết quả incremental?
