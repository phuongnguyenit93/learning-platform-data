# Đánh giá mức tái sử dụng so với độ phức tạp trong Aspect/AOP

**Aspect-Oriented Programming (AOP)** giúp đóng gói những mối quan tâm cắt ngang — logging, tracing, metrics, kiểm toán, kiểm tra quyền, transaction, retry hoặc quản lý tài nguyên — thay vì rải cùng logic vào nhiều phương thức nghiệp vụ. Một lời hứa hấp dẫn là **tái sử dụng**: một aspect hoặc một khung advice có thể áp dụng cho nhiều join point. Nhưng mỗi lớp trừu tượng bổ sung cũng có giá: người đọc phải hiểu pointcut, thứ tự aspect, binding, phạm vi weaving, vòng đời instance, các đường short-circuit và tác động của advice lên kết quả hoặc ngoại lệ.

Vì vậy, câu hỏi của bài không phải “nên tạo bao nhiêu aspect?”, mà là: **mức tái sử dụng thực sự mang lại có lớn hơn chi phí hiểu, thay đổi, kiểm thử và vận hành trừu tượng đó không?**

Một bộ ghi log đơn giản dùng chung ở 20 phương thức có thể tiết kiệm nhiều công sức và giảm sai khác. Nhưng một “siêu aspect” nhận hàng chục cờ cấu hình như `isAudit`, `doRetry`, `secure`, `transactional`, `cache` có thể tạo ra hàng trăm tổ hợp hành vi khó kiểm chứng. Tái sử dụng nhiều dòng mã không đồng nghĩa cải thiện thiết kế nếu phải trả bằng **coupling ngầm và độ phức tạp hành vi**.

Bài này bàn về **Aspect/AOP cơ bản và nâng cao nói chung**. Các ngôn ngữ/công cụ có khả năng pointcut, advice, kế thừa aspect, weaving, proxy và instantiation khác nhau. Ví dụ Java 17 sử dụng **JDK dynamic proxy với interceptor tái sử dụng**, không giả định mọi hệ AOP có cùng API.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **tái sử dụng logic**, **tái sử dụng định nghĩa pointcut**, **tái sử dụng cấu hình** và **tái sử dụng hợp đồng vận hành**.
2. Nhìn thấy chi phí của abstraction qua số điểm mở rộng, sự phụ thuộc giữa aspect, phạm vi ảnh hưởng khi sửa và độ khó debug.
3. Quyết định khi nào nên để code lặp nhỏ, khi nào nên trích helper/service, khi nào nên tạo aspect hoặc abstract aspect.
4. Đo lợi ích theo số lỗi tránh được, thời gian thay đổi, độ nhất quán, khả năng kiểm thử và tác động lên runtime.
5. Đánh giá **pointcut quá rộng**, join point bị bỏ sót, advice precedence, retry, short-circuit và state theo lời gọi.
6. Phân biệt **những concern thực sự cùng một hợp đồng** với concern chỉ tình cờ có cùng vài dòng code.
7. Sử dụng một ma trận chấm điểm hoặc tính toán chi phí giả định mà **không ngụy tạo độ chính xác**.
8. Viết Java 17 dùng một khung observation tái sử dụng nhưng cấu hình phạm vi đơn giản và giữ nguyên return/throw.
9. Kiểm thử các trường hợp bình thường, lỗi, chồng pointcut, cấu hình sai, đường bypass và tải cao.
10. Biết khi nào nên **dừng trừu tượng hóa**, tách aspect lớn và thay kế thừa bằng composition.

## 2. “Tái sử dụng” trong AOP gồm những gì?

Cần tách ít nhất năm cấp:

| Cấp | Thành phần được dùng chung | Ví dụ | Rủi ro |
| --- | --- | --- | --- |
| **Logic thuần** | Hàm định dạng, phép đo, serializer | `formatOperationName()` | Thường thấp nếu API rõ |
| **Advice template** | Khung before/proceed/after/finally | `observe(next)` | Hợp đồng lỗi hoặc retry bị dùng chung quá mức |
| **Pointcut definition** | Tập join point được đặt tên | “Execution của các thao tác xử lý đơn” | Wildcard kéo thêm join point ngoài ý định |
| **Aspect abstraction** | Abstract aspect, base class, policy hooks | Cùng khung trace, khác nhóm method | Kế thừa, instance scope và version coupling |
| **Cross-cutting architecture** | Bộ policy, cấu hình và thứ tự áp dụng xuyên module | Pipeline Auth → Audit → Target | Coupling/precedence, trạng thái, hiệu ứng và độ phủ |

**Giảm số dòng** chỉ là một phần rất nhỏ của giá trị. Tái sử dụng có thể cho lợi ích lớn hơn: thay một quy tắc lọc dữ liệu nhạy cảm ở một nơi; thống nhất nghĩa của metric; sửa bug bảo toàn ngoại lệ trên toàn bộ điểm can thiệp; tăng khả năng kiểm tra một policy bảo mật.

Ngược lại, một abstraction có thể có rất ít dòng nhưng nhiều **trạng thái ẩn**: “Nếu `attemptNumber > 1`, trừ khi `cacheHit`, bỏ `afterReturn` nếu `async`, trừ phương thức thuộc package X...”. Tính phức tạp này không hiện ra khi chỉ đếm LOC.

### 2.1. Tái sử dụng mã không phải tái sử dụng ngữ nghĩa

Hai advice đều ghi một dòng `System.out.println` nhưng khác hợp đồng:

- Advice A ghi **mọi yêu cầu truy cập**, kể cả bị từ chối.
- Advice B chỉ ghi **giao dịch đã cam kết bền vững**.
- Advice C chỉ là **trace hỗ trợ**, được phép bỏ mẫu khi exporter down.

Không nên gộp A/B/C thành một observer chung chỉ vì cùng gọi một logger. Chính sách về thời điểm chạy, retry, lỗi backend, nguồn dữ liệu và mức bắt buộc **không giống nhau**.

Một abstraction tốt chia sẻ **phần bất biến thực sự giống nhau** và để các khác biệt quan trọng hiện rõ, thay vì giấu chúng sau những cờ khó đọc.

## 3. Chi phí có thể xuất hiện ở đâu?

Một aspect tái sử dụng cần được xem ở toàn vòng đời:

1. **Thiết kế:** xác định pointcut và contract đủ tổng quát.
2. **Xây dựng:** viết weaver/configuration, binding, aspect base, helper và tests.
3. **Hiểu và bảo trì:** developer cần truy ngược đường chạy qua advice trước khi nhìn target.
4. **Thay đổi:** sửa một abstraction có thể tác động tới nhiều module.
5. **Kiểm thử:** tất cả nhóm join point, return/throw, order và đường không khớp.
6. **Tích hợp:** phiên bản Java, build plugin, class loader, module, woven artifact.
7. **Vận hành:** overhead, logs/metrics, lỗi do aspect, startup, hot reload.
8. **Gỡ bỏ:** nếu trừu tượng sai, phải tháo nó ở bao nhiêu caller và cấu hình?

Một câu “chỉ cần một aspect cho mọi thứ” thường chỉ tính **chi phí viết**, bỏ qua phần còn lại.

### 3.1. Độ phức tạp tại điểm gọi

Trong lập trình thông thường, lời gọi `service.place()` thường đủ để biết đi tới một method. Với AOP, có thể tồn tại:

```text
Caller
  -> proxy or woven join point
     -> authorization aspect
        -> retry aspect
           -> transaction aspect
              -> metrics aspect
                 -> target
```

Một lỗi có thể phát sinh **trước khi target được gọi**, trong target, sau return hoặc trong finally. Nếu những aspect được tái sử dụng toàn ứng dụng, một lần sửa pointcut có thể ảnh hưởng rất nhiều đường gọi.

Điểm cân bằng là **lợi ích tập trung chính sách** có vượt chi phí hiểu chuỗi ấy hay không.

## 4. Dấu hiệu có lợi từ tái sử dụng

Một concern là ứng viên tốt nếu thỏa nhiều điều kiện:

- Có ít nhất vài điểm cùng một **bất biến**, không chỉ giống vài từ khóa.
- Cần sửa đồng loạt để tránh sai khác về bảo mật hoặc tính đúng.
- Có **đầu vào/đầu ra rõ** từ join point; ít cần state bí mật từ aspect khác.
- Advice không tùy tiện thay đổi kết quả, ngoại lệ và số lần gọi target.
- Tập join point có thể chọn **chính xác và kiểm thử được**.
- Policy có ownership và vòng đời độc lập với nghiệp vụ.
- Chi phí test chung thấp hơn việc duy trì nhiều bản sao.
- Những biến thể có thể diễn đạt bằng **ít tham số có nghĩa**.
- Team có thể hiểu được scope/precedence mà không cần lần theo nhiều lớp kế thừa.
- Công cụ weaving/proxy đã có trong hệ thống và hoạt động ổn định.

Ví dụ hợp lý: mọi request được phép mang cùng **correlation metadata** và có chuẩn ghi log an toàn. Một library nhỏ xử lý chuẩn hóa tên, redaction và vòng đời scope có thể giảm lỗi hơn nhiều bản tự viết.

### 4.1. Một thay đổi được nhân rộng là lợi ích hay rủi ro?

Khi thay một advice dùng chung, tất cả join point liên quan nhận thay đổi. Đó là:

- **Lợi ích** nếu điều đó là yêu cầu thống nhất.
- **Rủi ro lan truyền** nếu các nhóm dùng abstraction thực ra cần contract khác.

Tính tổng quát phải đi đôi với **phạm vi sở hữu rõ ràng** và regression test đủ mạnh.

## 5. Những tín hiệu của trừu tượng hóa quá mức

Cảnh báo khi một abstract aspect/policy:

1. Có nhiều cờ Boolean điều khiển các nhánh không liên quan.
2. Dùng nhiều subclass chỉ để đổi một literal rất nhỏ.
3. Phải đọc 5–7 file mới thấy được một đường `proceed`.
4. Dùng wildcard pointcut rộng vì không biết domain nào sẽ áp.
5. Cần ghi ngoại lệ/thành phần “trường hợp riêng” thường xuyên.
6. Có thứ tự precedence thay đổi theo môi trường, khó test.
7. Cần static/ThreadLocal context để truyền dữ liệu ngầm giữa các aspect.
8. Cùng một exception được xử lý theo nhiều chính sách trái nhau trong một template.
9. Chuyển từ một framework/toolchain khác trở nên quá đắt vì mọi business logic phụ thuộc API AOP.
10. Thêm một tính năng nhỏ làm nảy sinh nhiều tổ hợp cấu hình và test hơn giá trị nó tạo.
11. Khi debug phải tắt nhiều aspect mới cô lập được nguyên nhân.
12. Một “base aspect” được kế thừa vì tiện, dù không có quan hệ **is-a** về ngữ nghĩa.

Không phải có nhiều tham số là luôn xấu; vấn đề là **các trục biến thiên tương tác lẫn nhau**. Ví dụ 5 cờ độc lập có thể tạo tối đa 32 tổ hợp. Nếu mỗi tổ hợp có ý nghĩa khác về retry/audit/security, phải có cách kiểm soát các kết hợp hợp lệ, không chỉ có unit test từng cờ.

## 6. Tách ba loại chi phí: cố định, biên và thay đổi

Một cách đánh giá hữu ích:

```text
Tổng chi phí ước tính =
  thiết kế + triển khai ban đầu
  + tích hợp/weaving
  + kiểm thử/đào tạo
  + bảo trì trên các lần thay đổi dự kiến
  + chi phí vận hành và rủi ro lỗi
```

Đây là **mô hình tư duy**, không phải công thức tài chính có độ chính xác tự động. Có thể dùng giờ công, độ phức tạp định tính hoặc số lỗi đã quan sát; tránh cộng tùy ý “điểm kỹ thuật” rồi giả vờ là tiền thật.

### 6.1. Chi phí ban đầu

Tách thành một aspect dùng chung có thể cần:

- Chốt hợp đồng observation/guard.
- Định nghĩa pointcut theo loại join point được tool hỗ trợ.
- Cấu hình thứ tự, binding, exception handling.
- Thêm build/weaving, compatibility tests.
- Đào tạo team đọc lời gọi xuyên advice.

Nếu hệ chỉ có **hai điểm áp** và logic rất nhỏ, chi phí ban đầu có thể lớn hơn việc giữ hai đoạn code rõ ràng.

### 6.2. Chi phí thêm một điểm áp dụng

Với một abstraction đã ổn định, thêm điểm thứ 20 có thể rất rẻ: chỉ cần thêm một rule pointcut và test coverage. Nhưng nếu mỗi điểm phải tạo subclass, thêm flags và đặc biệt hóa thứ tự, **chi phí biên không còn thấp**.

Hãy đo: “Để áp cùng chính sách cho một method mới, có bao nhiêu file cần sửa, bao nhiêu test cần bổ sung, và có bao nhiêu thành phần khác có thể bị ảnh hưởng?”

### 6.3. Chi phí sửa quy tắc chung

Nếu một chính sách redaction cần thay ở 15 nơi độc lập, lỗi sửa sót dễ xảy ra. Một helper/aspect dùng chung có lợi. Tuy vậy nếu chỉ 6 trong 15 nơi cần luật mới, một abstraction áp tất cả có thể tạo **breaking change**; cần phân biệt policy versions hoặc tách trách nhiệm.

## 7. Ví dụ tính toán giả định: khi nào hòa vốn?

Giả sử một nhóm cần cùng một cơ chế telemetry ở N nhóm method. Đây là **số liệu giả định phục vụ học**, không phải benchmark.

| Hạng mục | Viết riêng ở từng nơi | Một abstraction dùng chung |
| --- | --- | --- |
| Chi phí ban đầu | 1,5 giờ cho mỗi nhóm | 10 giờ thiết kế, test và tích hợp |
| Chi phí nối mỗi nhóm tiếp theo | 1,5 giờ | 0,5 giờ cấu hình và test |
| Chi phí một lần thay đổi chung | 1 giờ cho mỗi nhóm | 3 giờ sửa + regression |
| Phụ thuộc runtime/tooling | Ít | Có, phải kiểm soát |
| Rủi ro sửa sót hàng loạt | Cao hơn khi N lớn | Giảm, nhưng blast radius tăng |

Nếu chỉ tính **thiết lập ban đầu**:

```text
Separate(N) = 1.5 × N
Reusable(N) = 10 + 0.5 × N
Break-even: 1.5N = 10 + 0.5N  => N = 10
```

N = 3: viết riêng khoảng **4,5 giờ**, abstraction khoảng **11,5 giờ** theo giả định. N = 20: viết riêng **30 giờ**, abstraction **20 giờ**.

Nhưng nếu có ba lần đổi chung, mô hình cần cộng chi phí đổi mỗi nhánh hoặc một lần sửa abstraction. Nếu một cú sửa abstraction tạo regression diện rộng, con số “3 giờ” có thể quá lạc quan. Bởi vậy đây là **công cụ hỏi đúng câu hỏi**, không phải quy tắc “có 10 điểm thì phải dùng AOP”.

### 7.1. Chi phí không đồng nhất theo điểm can thiệp

Một method chạy mỗi ngày và một method chạy hàng triệu lần/giây có chi phí runtime khác nhau. Cùng một advice đo trace có thể chấp nhận được ở nhánh I/O chậm nhưng gây overhead rõ ở hot path.

Một lời gọi có dữ liệu đã cho phép logging khác với một lời gọi có credential/payload nhạy cảm. **Đếm số join point không đủ** để quyết định dùng chung.

### 7.2. Ước lượng theo khoảng, không theo một con số

Nếu không có số thực, ghi rõ khoảng:

- Thiết lập abstraction: **8–14 giờ** giả định.
- Test mỗi điểm bổ sung: **0,3–1 giờ** giả định.
- Số lần thay đổi policy trong năm: **1–5** giả định.

Làm kịch bản tốt/xấu để thấy kết luận có đảo không. Nếu chỉ một thay đổi nhỏ trong giả định khiến kết luận đảo chiều, hãy chọn giải pháp **dễ đảo ngược**: helper method hoặc policy object trước khi đưa thêm cơ chế weaving phức tạp.

## 8. Các thước đo kỹ thuật tốt hơn số dòng code

| Thước đo | Cách quan sát | Vì sao hữu ích |
| --- | --- | --- |
| **Số lỗi lặp lại** | Bug cùng nguyên nhân ở nhiều nơi | Tái sử dụng có thể xóa một lớp sai khác |
| **Thời gian thay đổi quy tắc chung** | Từ yêu cầu đến test/deploy | Đo lợi ích bảo trì |
| **Blast radius** | Số module/join point bị ảnh hưởng bởi một sửa đổi | Đánh giá rủi ro tập trung |
| **Độ rõ của ownership** | Ai được sửa chính sách và pointcut? | Giảm cấu hình xung đột |
| **Pointcut precision** | Điểm mong muốn chọn đủ, điểm không mong muốn loại đúng | Đánh giá chất lượng áp dụng |
| **Advice overlap** | Join points bị nhiều aspect cùng chọn | Dự báo trùng hành vi và precedence |
| **Số cấu hình hợp lệ** | Những tổ hợp policy thực sự được hỗ trợ | Đo độ phức tạp kiểm thử |
| **Khó khăn debug** | Số bước/tool cần truy ra effect | Đo chi phí nhận thức |
| **Runtime overhead** | Latency, allocations, GC và throughput | Kiểm soát hot path |
| **Phạm vi phụ thuộc tooling** | Compiler/weaver/runtime/plugins | Đánh giá lock-in và build fragility |
| **Tốc độ mở rộng** | Nơi phải sửa để thêm một join point | Đánh giá chi phí biên |
| **Tỷ lệ test hợp đồng** | Return/throw/async/bypass/overlap | Đánh giá an toàn của abstraction |

### 8.1. “Số dòng giảm” không tự động có nghĩa chất lượng tăng

Một triển khai dùng một method dài với nhiều nhánh điều kiện có thể ít dòng hơn ba aspect nhỏ, nhưng khó hiểu hơn. Đánh giá **độ phức tạp cyclomatic/cognitive**, số trạng thái có thể đi qua và khả năng người mới giải thích kết quả.

### 8.2. Đếm đúng đơn vị

Một lời gọi business có thể có nhiều **attempts** do retry, nhiều **advice executions** do pointcut overlap, và chỉ một **committed effect** hoặc không có. Nếu muốn đo lợi ích reusable aspect, cần định nghĩa thứ đang đếm: logical request, invocation, attempt, successful return hay commit.

## 9. Điểm quan trọng nhất của AOP: độ chính xác pointcut

Một reusable advice có giá trị chỉ khi nó chạy tại đúng những điểm cần thiết. Tập các join point được chọn có thể biểu diễn:

```text
Expected = tập join point chính sách phải áp
Selected = tập join point pointcut thực tế chọn

Misses = Expected - Selected
Unexpected = Selected - Expected
```

- **Misses** làm thiếu instrumentation hoặc thiếu chính sách bắt buộc.
- **Unexpected** tạo overhead, log sai, recursion hoặc thay đổi nghiệp vụ ngoài phạm vi.
- **Overlap** với những aspect khác có thể nhân đôi advice hay đổi thứ tự.

Có thể dùng một bảng test để liệt kê điểm **phải khớp** và **không được khớp**, thay vì chỉ thử một đường happy path.

### 9.1. Wildcard có chi phí ẩn

Một pointcut kiểu “mọi phương thức trong mọi service” có thể rất dễ tái sử dụng. Nhưng khi nhóm thêm một method nội bộ được gọi hàng triệu lần, nó cũng bị instrument. Nếu advice ghi I/O log, hệ có thể chậm đột ngột dù code nghiệp vụ mới không trực tiếp import aspect.

Nên ưu tiên **phạm vi hẹp, có chủ đích** và sử dụng marker/contract tường minh khi phù hợp. Với thao tác nhạy cảm, không chỉ dựa vào tên class/package để kết luận đã bảo vệ mọi đường effect.

### 9.2. Join point kind và khả năng công cụ

Cùng từ “intercept phương thức” có thể có hai mục tiêu: **method call** tại caller và **method execution** tại target. Một JDK proxy chỉ áp cho lời gọi **qua interface proxy**; nó không tự xử lý mọi field access, constructor, private method hay self-invocation trên target.

Lợi ích tái sử dụng phải tính cả **độ phủ thực tế** và chi phí build/deploy woven artifact. Một pointcut “đẹp” nhưng không bao phủ đường chạy quan trọng làm thiết kế sai.

## 10. Sự phức tạp do nhiều aspect phối hợp

Một aspect độc lập có thể tương đối đơn giản. Khi nhiều aspect cùng chọn một điểm:

```text
Metrics(Authorization(Cache(Retry(Transaction(Target)))))
```

thì thứ tự có thể thay đổi ý nghĩa:

- Metrics ngoài Authorization có thể đếm cả lời gọi bị từ chối; bên trong không thấy yêu cầu bị short-circuit.
- Cache nằm ngoài Authorization có thể trả cache hit mà guard bên trong không chạy.
- Retry ngoài Transaction có thể tạo transaction riêng mỗi attempt; cấu trúc đảo có thể thử nhiều lần trong cùng transaction.
- Audit sau target nhưng trước outer transaction commit không có bằng chứng “đã cam kết”.
- Một fallback có thể nuốt ngoại lệ mà observer ngoài muốn thấy.

**Tái sử dụng một khung around advice không làm những phụ thuộc này tự biến mất.** Cần contract về thứ tự, scope, kết quả và lỗi cho từng tổ hợp thật sự dùng.

### 10.1. Có nên kế thừa một “siêu aspect” chứa tất cả?

Thông thường nên thận trọng. Một base chung cho authentication, retry, audit, cache và metrics khiến subclass phải hiểu tất cả nhánh bất chấp nó chỉ cần một chức năng. Có nhiều trạng thái không hợp lệ, bảo trì khó và rủi ro fail-open.

Hãy tách những concern có **bất biến khác nhau** thành components riêng; phối hợp bằng precedence rõ hoặc coordinator cho nghiệp vụ quan trọng. Dùng inheritance khi có một **template hành vi thống nhất**, dùng composition khi các chính sách chỉ cộng tác.

### 10.2. Không dùng advice precedence thay cho giao thức atomic

Nếu bắt buộc lưu nghiệp vụ và audit bền vững cùng nhau, chỉ đổi thứ tự Transaction/Audit không bảo đảm atomicity với hệ thống bên ngoài. Có thể cần transaction boundary, outbox, idempotency và đối soát. Đây là **ngữ nghĩa nghiệp vụ**, không phải thứ có thể trừu tượng hóa hết bằng pointcut.

## 11. Chọn hình thức tái sử dụng phù hợp

Không phải mọi tái sử dụng đều cần một abstract aspect.

| Lựa chọn | Khi phù hợp | Điểm cần đề phòng |
| --- | --- | --- |
| **Giữ code trực tiếp** | Ít nơi, logic ngắn, ít thay đổi, khác nghĩa | Trùng lặp có thể lan rộng sau này |
| **Hàm/helper chung** | Cùng phép xử lý thuần, không cần chặn join point | Tránh helper trở thành nơi giữ state ngầm |
| **Strategy/policy object** | Thay một thuật toán trong contract rõ | Nhiều cấu hình và dependency tiềm ẩn |
| **Decorator/interceptor** | Muốn wrapper ở ranh giới do caller lựa chọn | Đường đi ngoài wrapper có thể bypass |
| **Aspect riêng** | Concern cắt ngang nhiều điểm, pointcut ổn định | Coverage, tooling, thứ tự |
| **Abstract aspect** | Chung advice skeleton, concrete pointcuts khác | Kế thừa phụ thuộc ngôn ngữ, hooks và lifecycle |
| **Named pointcuts** | Chia sẻ tập join point, không nhất thiết cùng advice | Tập điểm có thể quá rộng |
| **Composition nhiều aspects** | Chính sách tách biệt, phối hợp theo contract | Precedence/overlap |
| **Coordinator nghiệp vụ** | Cần bất biến, transaction hoặc workflow chặt | Không nên giấu logic nghiệp vụ cốt lõi trong aspect |

### 11.1. Quy tắc ra quyết định theo biến thiên

Nếu phần **giống nhau** là một thuật toán nhỏ: trích **helper**.

Nếu phần giống nhau là **khung điều khiển advice** còn khác biệt chỉ ở pointcut/label: một **base aspect** hoặc interceptor template có thể hợp lý.

Nếu các phần cần **thứ tự phối hợp** nhưng nghiệp vụ khác nhau: **composition** và contract precedence.

Nếu có **nguyên tử, audit bền vững, retry hiệu ứng**, cân nhắc một **coordinator/service** ở ranh giới nghiệp vụ thay vì cố tổng quát hóa advice.

### 11.2. Một abstraction dễ thay thế thường thắng sớm

Khi chưa rõ hai điểm có thật sự cùng nghĩa, có thể giữ hai thành phần độc lập nhưng dùng chung **một hàm thuần**. Sau khi các yêu cầu thay đổi thực sự cho thấy một bất biến lặp lại, mới đưa lên abstraction cấp aspect.

Đây không phải chống tái sử dụng; nó là **giảm cam kết sớm vào một trừu tượng chưa có bằng chứng**.

## 12. Ví dụ Java 17: tái sử dụng khung advice, không gộp mọi chính sách

Để thấy mức tái sử dụng hợp lý, ta xây một bộ interception rất nhỏ bằng **JDK dynamic proxy**:

- Một `Rule` chứa **nhãn** và điều kiện chọn operation.
- Một hàm `invokeAt` dùng chung khung `before → proceed → returned/throw → finally` cho mọi rule phù hợp.
- Rule `BASE` áp với mọi lời gọi `run`; rule `FIN` chỉ áp khi operation bắt đầu bằng `bill-`.
- Ở operation `bill-1`, hai rule **cùng khớp** nên sinh hai lớp log lồng nhau; đó không phải lỗi Java inheritance.
- Với operation `bad`, target ném ngoại lệ; chương trình **giữ lỗi gốc**, không trả fallback giả.
- Một lời gọi **trực tiếp target gốc** không đi qua proxy; đây là giới hạn được kiểm chứng, không giấu sau API.
- Ví dụ không chứa retry/auth/audit/transaction: chúng không chia sẻ cùng hợp đồng quan sát.

**Đây là ví dụ tái sử dụng logic interceptor với Java thuần, không phải định nghĩa native pointcut/advice của một ngôn ngữ AOP.**

Lưu thành `ReuseComplexityDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.function.Predicate;

public class ReuseComplexityDemo {
    public interface WorkPort {
        String run(String operation);
    }

    public static final class WorkService implements WorkPort {
        int calls;

        @Override
        public String run(String operation) {
            calls++;
            System.out.println("TARGET " + operation);
            if ("bad".equals(operation)) {
                throw new IllegalArgumentException("invalid:bad");
            }
            return "ok:" + operation;
        }
    }

    record Rule(String tag, Predicate<String> selected) {}

    static Object invokeTarget(
            Method method, Object target, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Object invokeAt(
            int index, List<Rule> rules,
            Method method, Object target, Object[] args)
            throws Throwable {
        if (index == rules.size()) {
            return invokeTarget(method, target, args);
        }

        Rule rule = rules.get(index);
        String operation = (String) args[0];
        if (!rule.selected().test(operation)) {
            return invokeAt(index + 1, rules, method, target, args);
        }

        System.out.println(rule.tag() + " before " + operation);
        try {
            Object result = invokeAt(
                    index + 1, rules, method, target, args);
            System.out.println(rule.tag() + " returned " + result);
            return result;
        } catch (Throwable error) {
            System.out.println(rule.tag() + " threw "
                    + error.getClass().getSimpleName());
            throw error;
        } finally {
            System.out.println(rule.tag() + " finally");
        }
    }

    static WorkPort wrap(WorkPort target, List<Rule> rules) {
        return (WorkPort) Proxy.newProxyInstance(
                WorkPort.class.getClassLoader(),
                new Class<?>[] { WorkPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("run")
                            || method.getParameterCount() != 1) {
                        throw new UnsupportedOperationException(
                                method.getName());
                    }
                    return invokeAt(0, rules, method, target, args);
                });
    }

    public static void main(String[] args) {
        WorkService target = new WorkService();
        WorkPort observed = wrap(target, List.of(
                new Rule("BASE", op -> true),
                new Rule("FIN", op -> op.startsWith("bill-"))));

        System.out.println("CALL " + observed.run("ship-1"));
        System.out.println("CALL " + observed.run("bill-1"));

        try {
            observed.run("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }

        System.out.println("DIRECT " + target.run("bill-2"));
        System.out.println("TOTAL_TARGET_CALLS " + target.calls);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReuseComplexityDemo.java
java ReuseComplexityDemo
```

**Stdout dự kiến chính xác:**

```text
BASE before ship-1
TARGET ship-1
BASE returned ok:ship-1
BASE finally
CALL ok:ship-1
BASE before bill-1
FIN before bill-1
TARGET bill-1
FIN returned ok:bill-1
FIN finally
BASE returned ok:bill-1
BASE finally
CALL ok:bill-1
BASE before bad
TARGET bad
BASE threw IllegalArgumentException
BASE finally
CAUGHT invalid:bad
TARGET bill-2
DIRECT ok:bill-2
TOTAL_TARGET_CALLS 4
```

### 12.1. Những gì được tái sử dụng

Logic `before/proceed/returned/throw/finally` nằm trong **một** hàm `invokeAt`. Hai rule không lặp lại điều khiển ngoại lệ; chúng chỉ cung cấp **nhãn và tập operation**. Nếu muốn sửa dạng thông báo, có thể sửa khung chung.

**Giá trị:** nhất quán trong cách ghi return/throw, không quên finally giữa hai implementations.

**Chi phí:** mọi lời gọi qua proxy cần đi qua danh sách rule và call recursion. Người đọc phải biết `invokeAt` và `Predicate` mới hiểu vì sao operation `bill-1` có hai lớp log.

### 12.2. Vì sao `ship-1` chỉ có BASE?

Rule BASE chọn mọi operation; rule FIN chỉ chọn tên bắt đầu `bill-`. Khi `ship-1` đi vào FIN, rule không khớp và lập tức chuyển tiếp, không in log FIN. Target được gọi một lần và trả `ok:ship-1`.

### 12.3. Vì sao `bill-1` có hai bộ log?

Cả BASE và FIN cùng chọn `bill-1`. Chuỗi tương đương:

```text
BASE(FIN(Target))
```

Nó chạy BASE before, FIN before, target, FIN returned/finally, rồi BASE returned/finally. **Overlap được chủ động phơi bày**, không lén deduplicate vì các rule dùng chung hàm.

### 12.4. Vì sao nhánh lỗi giữ nguyên `IllegalArgumentException`?

Target ném lỗi sau khi tăng counter. Reflection bọc lỗi trong `InvocationTargetException`; `invokeTarget` lấy `getCause()`. Hàm chung in lỗi, rồi **ném lại cùng throwable**. Caller bắt đúng loại lỗi gốc và thấy thông điệp `invalid:bad`.

Nếu triển khai observer thực sự có một exporter dễ lỗi, cần **tách phạm vi catch của exporter** khỏi phạm vi `proceed`; nếu không, lỗi từ observer có thể che lỗi target. Ví dụ chỉ dùng `System.out` trong đường thực thi dự kiến.

### 12.5. Vì sao lời gọi trực tiếp không có log?

`target.run("bill-2")` dùng đối tượng WorkService gốc, không đi qua proxy. Việc ta xây một reusable interceptor **không biến toàn bộ lớp target thành woven class** và không bảo vệ tất cả đường gọi. Đây là chi phí kiến trúc cần tính nếu tái sử dụng qua proxy: đảm bảo caller có đúng reference và kiểm thử coverage.

### 12.6. Hạn chế để tránh áp dụng sai

- Điều kiện FIN dựa trên **prefix của dữ liệu operation**, không phải một native pointcut về method signature. Một thiết kế AOP thực nên chọn join point đúng theo loại method/annotation/type được hỗ trợ.
- Handler chỉ phục vụ method `run(String)` ở các đường của demo. Nó chưa thiết kế đầy đủ `equals`, `hashCode`, `toString` và mọi overload có thể có.
- `Predicate` là code Java thông thường, có thể ném exception hoặc chiếm nhiều CPU; rule không tự vô hại.
- Không có retry, transaction, audit bền vững hay kiểm tra quyền. Đừng nhét chúng vào chung template observation mà không thiết kế contract mới.
- Không có weaving vào body target, field access hay constructor; direct calls và self-invocation có thể bypass.
- Trạng thái counter chỉ tăng trong chương trình chạy tuần tự này; với concurrent calls cần xác định tính thread-safe nếu dùng counter trong sản xuất.
- Nếu muốn chỉ **một** log cho mỗi logical request, hai rule overlap có thể không phù hợp; khi đó phải quy định rõ precedence/deduplication.

## 13. Ví dụ phản chứng: trừu tượng quá rộng

Giả sử một nhóm tạo một aspect dùng chung:

```text
UniversalAspect(config):
    if config.cacheEnabled and hit: return cachedValue
    if config.checkPermission: authorize()
    if config.retry: loop:
        if config.transaction: beginTransaction()
        runTarget()
    if config.audit: audit()
    if config.metrics: emitMetric()
```

Đây là **giả mã thiết kế cần cảnh giác**, không phải một mẫu áp dụng mặc định. Những nhánh tưởng độc lập lại tương tác:

- Cache hit có bỏ qua kiểm tra quyền không?
- Retry có mở transaction riêng mỗi attempt?
- Audit xảy ra trước hay sau commit?
- Nếu metrics backend lỗi sau target, caller có thấy lỗi không?
- Có thể trả cached value cho operation ghi không?
- Những flags được bật/tắt ở runtime thì trạng thái transaction xử lý thế nào?

Nếu một abstraction đòi trả lời quá nhiều câu hỏi thuộc **những hợp đồng khác nhau**, hãy tách nó ra. Có thể dùng helper chung cho logging format, nhưng để authorization, retry, transaction, audit là các policies tách biệt với điều phối rõ.

### 13.1. “Một chỗ để sửa” có thể là một điểm lỗi tập trung

Tập trung logic đúng giúp sửa lỗi đồng loạt. Tập trung mọi thứ vào một hệ thống điều kiện có thể khiến một thay đổi nhỏ ảnh hưởng hàng nghìn lời gọi không liên quan. Cần **đánh giá phạm vi tác động trước mỗi thay đổi**, có canary/feature rollout phù hợp và regression tests trên những điểm can thiệp quan trọng.

## 14. Tái sử dụng qua kế thừa aspect: khi nào đáng giá?

Nếu ngôn ngữ AOP hỗ trợ **abstract aspect** và **abstract pointcut**, một base aspect có thể định nghĩa advice skeleton, còn concrete aspects cung cấp pointcuts cho từng miền.

Mô hình:

```text
AbstractObservationAspect
  + shared advice: enter/return/throw/finally
  + abstract selectedOperations()

OrderObservation
  + selectedOperations() = OrderService operations

InvoiceObservation
  + selectedOperations() = InvoiceService operations
```

**Lợi ích:** định nghĩa khung advice một lần, các concrete specializations chỉ cấu hình phạm vi.

**Chi phí:** phụ thuộc cơ chế inheritance của ngôn ngữ, version của compiler/weaver, binding signatures, visibility, instantiation policy và giao nhau giữa pointcuts.

Không mặc định một subclass có thể **override advice** như override Java method; lời khai báo advice, việc kế thừa nó và precedence của các aspect có luật ngữ nghĩa riêng theo công cụ. Nếu chỉ cần tái sử dụng formatter, **helper/delegate** có thể ít rủi ro hơn một base aspect.

### 14.1. Cây kế thừa càng sâu, hợp đồng càng khó thấy

Một cây năm tầng có thể ép concrete aspect phải hiểu cả năm nhóm hooks. Khi sửa base, tất cả hậu duệ bị ảnh hưởng. Thường nên ưu tiên **một hoặc rất ít tầng**, giữ các điểm mở rộng ít và được kiểm thử, rồi dùng composition cho khác biệt độc lập.

### 14.2. State kế thừa không tự tách theo invocation

Field `currentRequest` trên base, nếu concrete instance dùng chung giữa các request, có thể gây race và giữ dữ liệu lâu. Điều kiện `cflow` chọn join point cũng **không tự tạo instance per-flow**; nếu ngôn ngữ có `percflow` hoặc cơ chế instantiation tương tự, phải xác minh riêng.

Một abstracion dùng chung tốt không nên đòi mọi concrete child giữ request object trong một mutable field suốt đời.

## 15. Chi phí kiểm thử tăng theo số chiều hành vi

Một rule mới có thể tương tác với:

- Nhánh target **return/throw**;
- Có/không có authorization;
- Cache **hit/miss**;
- Retry **1/N attempts**;
- Transaction **commit/rollback**;
- Advice lỗi **trước/sau effect**;
- Path qua **proxy/direct target**;
- Lời gọi **sync/async**;
- Một/nhiều aspects cùng khớp;
- Một hoặc nhiều thread.

Không phải lúc nào cũng cần test **mọi tổ hợp Cartesian**, nhưng phải tìm những trục có **tương tác ngữ nghĩa**. Pairwise testing có thể giúp phủ cấu hình thông thường, nhưng không thay thế các kịch bản có rủi ro cao như “retry sau commit” hoặc “cache bypass quyền”.

### 15.1. Ma trận kiểm thử tối thiểu cho aspect quan sát

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Một điểm được chọn | Advice chạy đúng theo contract |
| Một điểm không được chọn | Không chạy advice ngoài ý định |
| Hai concrete rules cùng khớp | Số lời gọi và thứ tự biết trước |
| Target trả bình thường | Giá trị trả đúng |
| Target ném ngoại lệ | Loại/cause ban đầu giữ nguyên |
| Advice logging ném lỗi | Hợp đồng xử lý lỗi telemetry đúng |
| Advice trong nested around | Before/after order đúng |
| Target được gọi trực tiếp | Phát hiện đường bypass nếu dùng proxy |
| Pointcut chọn nhiều overload | Không khớp nhầm chữ ký |
| Recursive call | Không tạo advice loop ngoài ý muốn |
| Singleton aspect đồng thời | Không ghi đè state per-request |
| Async method trả future | Không nhầm return future với completion |
| Cấu hình rule không hợp lệ | Bị từ chối rõ, không âm thầm mất guard |
| Artifact sau weaving | Code đang chạy thực sự chứa advice cần thiết |

### 15.2. Chỉ test “có log” là thiếu

Nếu một trace aspect chạy hai lần rồi target cũng chạy hai lần vì advice retry sai, test chỉ assert `contains("TRACE")` vẫn pass. Cần kiểm tra **số lần target được gọi, kết quả, ngoại lệ, tác dụng phụ** và **negative selection**.

## 16. Hiệu năng: đo phần nào?

Một lời gọi AOP có thể gồm:

```text
T_total =
  interception dispatch
  + pointcut/binding checks
  + advice body
  + target execution
  + downstream telemetry/IO
```

Đây là mô hình phân rã tương đối, không có bảo đảm tổng thời gian thực luôn cộng đơn giản dưới concurrency. Để đánh giá:

1. Lấy **baseline** không bật concern tương ứng nhưng cùng workload.
2. Bật từng concern riêng để xác định chi phí.
3. Bật tổ hợp được phép trong cấu hình thật.
4. Đo latency distribution, throughput, allocations, GC, CPU và network nếu phù hợp.
5. Tách chi phí pointcut/dispatch khỏi chi phí I/O logger/metrics.
6. Đo cả **no-match** và **match**, warmup JIT trước benchmark ổn định.
7. So sánh hiệu năng với lợi ích lỗi được tránh và tính nhất quán chính sách.

Không tuyên bố “AOP luôn nhanh/chậm hơn code trực tiếp”. Kết quả phụ thuộc **công nghệ, advice, số điểm và workload**.

### 16.1. Benchmark cần tránh sai số lớn

- Không chạy một lần ngắn rồi kết luận; JIT/warmup ảnh hưởng.
- Không đo benchmark trong khi in hàng nghìn dòng `System.out` rồi quy overhead về pointcut.
- Không so sánh hai nhánh có semantics khác nhau: một nhánh có I/O, nhánh kia không.
- Không bỏ qua concurrency và tỷ lệ điểm thực sự khớp pointcut.
- Không chỉ dùng trung bình nếu tail latency quan trọng.
- Với logging, thử các chế độ backend khỏe/chậm/down theo contract.

### 16.2. Mức tái sử dụng cao có thể tạo “hot-path surprise”

Một pointcut dùng lại khắp ứng dụng có thể vô tình bao cả getter nhỏ được gọi rất nhiều lần. Chỉ cần thêm một phép reflection, allocation hoặc serialize object ở advice, chi phí cộng dồn trở nên đáng kể. Một phương án có thể là **điểm chọn hẹp và sampling** phù hợp, không phải vội thay toàn bộ kiến trúc.

## 17. Góc nhìn bảo mật và rủi ro vận hành

Một concern cắt ngang có thể là **điều kiện bắt buộc**, không phải tùy chọn.

- **Authorization:** không xác minh được quyền thì không tự cho phép. Nếu proxy bị bypass, chính sách không còn được đảm bảo.
- **Audit bắt buộc:** không coi việc target trả bình thường là bằng chứng audit đã được ghi bền vững.
- **Privacy/redaction:** không lưu toàn bộ arguments/target trong singleton aspect nếu chỉ cần tên thao tác.
- **Retry:** không tự lặp effect không idempotent; xử lý trạng thái không chắc chắn sau timeout.
- **Resource cleanup:** dùng owner rõ, finally/AutoCloseable; đừng dựa vào GC.
- **Observability phụ trợ:** nếu fail-open cho exporter, chỉ được phép bỏ tín hiệu hỗ trợ theo hợp đồng; không che lỗi từ target.

Một reusable aspect làm thiếu một kiểm soát bắt buộc ở nhiều nơi là **rủi ro lan truyền lớn**, không phải chỉ lỗi cấu hình nhỏ. Cần có security review và test độ phủ ở điểm thật sự tạo effect.

## 18. Chỉ số định tính để đánh giá một thiết kế

Có thể chấm từng mục **Thấp / Trung bình / Cao**, có giải thích:

| Tiêu chí | Thấp (thuận lợi) | Cao (cần thận trọng) |
| --- | --- | --- |
| **Biến thể hành vi** | Một contract, vài tham số | Nhiều nhánh với semantics khác nhau |
| **Phụ thuộc thứ tự** | Độc lập | Nhiều precedence bắt buộc |
| **Pointcut variability** | Tập điểm ổn định | Wildcard/overload thay đổi liên tục |
| **State coupling** | Local/bất biến | Global, ThreadLocal, nhiều aspect trao đổi state |
| **Chi phí debug** | Trace rõ đường gọi | Chuỗi advice sâu, khó truy nguyên |
| **Blast radius** | Một module/nhóm nghiệp vụ | Nhiều dịch vụ nhạy cảm |
| **Tooling dependency** | Không thêm cơ chế mới | Cần weaving/runtime phức tạp |
| **Chi phí kiểm thử** | Ít nhánh độc lập | Nhiều tổ hợp có thể sai |
| **Khả năng tháo bỏ** | Chuyển về helper dễ | Mã nghiệp vụ phụ thuộc sâu vào AOP |
| **Lợi ích nhất quán** | Ít điểm cần đồng bộ | Nhiều điểm cùng một nghĩa và hay đổi |

Không cộng tổng các nhãn này như một “điểm chất lượng tuyệt đối”. Hãy nhìn **điểm nghẽn**: một rủi ro bảo mật cao có thể khiến thiết kế không phù hợp dù các mục khác rất đẹp.

## 19. Quy trình quyết định sáu bước

### Bước 1 — Viết bất biến, không viết công cụ trước

Ví dụ: “Mọi operation được đánh dấu là nhạy cảm phải được kiểm quyền trước effect; thiếu quyết định thì không được chạy.” Đây là **bất biến**. Chỉ sau đó mới chọn aspect, proxy, domain service hay một cơ chế khác.

### Bước 2 — Kiểm kê các vị trí thực sự cùng contract

Liệt kê **join point dự kiến**, phương thức nào cần áp, loại nào phải loại, dữ liệu đầu vào cần thiết, các nhánh return/throw. Đừng gộp chỉ vì hai đoạn log giống nhau.

### Bước 3 — Chọn cấp tái sử dụng thấp nhất đủ đáp ứng

Nếu một helper thuần giải quyết phần lặp, dùng helper. Nếu cần chặn nhiều join point thật sự, cân nhắc aspect. Nếu cần nhiều specialization cùng skeleton, xem abstract aspect khi ngôn ngữ hỗ trợ.

### Bước 4 — Vẽ luồng điều khiển và trách nhiệm lỗi

Phác họa thứ tự advice, vị trí short-circuit, retry, transaction, audit; chỉ rõ **mỗi thành phần có thể thay return/exception không** và cleanup thuộc owner nào.

### Bước 5 — Ước lượng và kiểm chứng bằng thí điểm

Chọn một nhóm method đại diện. Đo số file thay đổi, effort review, tính dễ debug, precision của pointcut và overhead. Đưa kết quả sang nhóm khác **chỉ khi** contract giống nhau.

### Bước 6 — Quy định điều kiện dừng hoặc đảo ngược

Ví dụ: “Nếu thêm nhóm nghiệp vụ thứ ba phải bổ sung hơn ba flags mới hoặc thay đổi semantics của base, tách abstraction”; “Nếu pointcut không bao phủ đường critical, chuyển guard về ranh giới nghiệp vụ đáng tin”.

Điều kiện dừng giúp tránh tâm lý tiếp tục dùng một framework phức tạp chỉ vì đã đầu tư công sức trước đó.

## 20. So sánh ba trường hợp thực tế về kiến trúc

### Trường hợp A — Chuẩn hóa correlation và logging

Có nhiều method dùng cùng quy tắc correlation ID, giới hạn dữ liệu log và timestamp. Ý nghĩa tương đối đồng nhất.

**Khuyến nghị thiết kế:** một helper/context owner chung và một aspect quan sát hoặc interceptor template có phạm vi rõ; dùng biến cục bộ/context đúng lifecycle. Đo overhead và tránh lưu request trong field dài hạn.

**Lợi ích:** sửa chính sách redaction một nơi, tránh bỏ sót cleanup. **Chi phí:** cấu hình pointcut, propagation qua async và giám sát exporter down.

### Trường hợp B — Cache và authorization

Hai concern đều có dạng around method, nhưng Cache có thể short-circuit còn Auth là điều kiện bắt buộc trước khi đọc dữ liệu nhạy cảm.

**Khuyến nghị thiết kế:** **không** gộp vào một base chỉ vì cả hai có `proceed`. Dùng policies riêng, quyết định order theo threat model và kiểm tra cache-hit path. Nếu target gốc có đường gọi khác, bảo vệ effect ở ranh giới đáng tin.

**Lợi ích:** contract rõ và có thể thay cache mà không thay quyền. **Chi phí:** cần test thứ tự và cache key theo phạm vi quyền.

### Trường hợp C — Audit đã commit và tracing tùy chọn

Cả hai có thể ghi một event, nhưng audit phải có bằng chứng effect đã cam kết; tracing có thể bị drop khi exporter quá tải.

**Khuyến nghị thiết kế:** chia sẻ hàm serialize/format **nếu có cùng schema an toàn**, nhưng giữ **hai chính sách lỗi và lifecycle khác nhau**. Với audit bền vững, cân nhắc outbox/coordinator theo nhu cầu.

**Lợi ích:** tránh biến một lỗi telemetry thành mất audit bắt buộc hoặc ngược lại khiến mọi giao dịch lỗi khi trace sink down.

## 21. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách cải thiện |
| --- | --- | --- |
| “Càng ít dòng càng tốt” | Bỏ qua complexity ẩn trong pointcut/config | Đo cost of change và test |
| Gộp các concern chỉ vì cùng `proceed` | Nghĩa retry/auth/audit khác nhau | Tách theo bất biến |
| Abstract aspect có quá nhiều flags | Tổ hợp cấu hình bùng nổ | Strategy nhỏ/composition |
| Dùng wildcard quá rộng | Match ngoài ý định, overhead, recursion | Pointcut hẹp và negative tests |
| Cho rằng kế thừa quyết định precedence | Trật tự advice là hợp đồng riêng | Test thứ tự/nesting |
| Coi `cflow` tự tạo instance per-request | State có thể chia sẻ sai | Kiểm tra instantiation policy |
| Lưu request trong singleton aspect | Race và memory retention | Local/scoped state |
| Chỉ test success | Không thấy exception/cleanup/short-circuit | Test return, throw, failure |
| Tái sử dụng một fallback cho mọi lỗi | Nuốt guard errors hoặc target errors | Phân loại policy bắt buộc/tùy chọn |
| Coi proxy là weaver toàn ứng dụng | Direct target/self-invocation bypass | Xác minh coverage |
| Coi audit = log | Mất cam kết bền vững, sai trạng thái commit | Contract và durable recording |
| Dùng retry mù để chữa lỗi advice | Tạo effect trùng | Idempotency và đối soát |
| Đo performance bằng log I/O rồi kết luận pointcut chậm | Không cô lập nguyên nhân | Benchmark từng thành phần |
| Không test version/build artifact | Weaving thiếu hoặc thay semantics | Artifact-level integration tests |
| Trì hoãn tách abstraction sai | Sunk cost, nhiều nhánh đặc biệt | Định nghĩa exit criteria |

## 22. Bài tập vận dụng và đáp án

### Bài 1 — Hai điểm có cùng log

Chỉ hai method cùng in `BEGIN` và `END`; method A bắt buộc rethrow lỗi, method B trả fallback. Có nên chia sẻ một around template?

**Đáp án:** Chưa nên gộp contract điều khiển thành một nếu semantics lỗi khác nhau. Có thể chia sẻ **formatter** nhỏ, còn nhánh lỗi phải tách hoặc có policy cực kỳ rõ.

### Bài 2 — Hai mươi method cùng policy

Có 20 method cần cùng một chuẩn che dữ liệu nhạy cảm trước khi log. Có thay đổi policy thường xuyên. Giá trị tái sử dụng chính là gì?

**Đáp án:** Một chính sách redaction thống nhất, giảm sửa sót và có test hợp đồng chung. Pointcut phải bao phủ đúng 20 method, không tự ghi payload nguyên dạng.

### Bài 3 — Overlap

Hai concrete observation aspects dùng chung base, cả hai chọn `invoice.create()`. Có chắc chỉ có một log vì chung base không?

**Đáp án:** Không. Một join point có thể nhận hai advice/concrete instances. Cần xem pointcut intersection và precedence.

### Bài 4 — Chi phí hòa vốn

Trong mô hình giả định, viết riêng tốn `1.5N` giờ, abstraction tốn `10 + 0.5N` giờ. N bao nhiêu thì hai bên bằng nhau?

**Đáp án:** N = 10. Đây chỉ là hòa vốn **chi phí ban đầu theo giả định**, không phải quy tắc quyết định mọi dự án.

### Bài 5 — Thứ tự

`Cache(Authorization(Target))` có thể return từ cache trước khi gọi Auth. Việc gom hai policy vào một class có tự sửa sai đó không?

**Đáp án:** Không. Phải bảo vệ điều kiện quyền ở mọi đường trả dữ liệu, và kiểm tra actual order/coverage; cấu trúc class không tự bảo đảm an toàn.

### Bài 6 — Đánh giá runtime

Một điểm nóng gọi 2 triệu lần/phút, một advice có reflection và serialization. Tái sử dụng cùng advice như các endpoint I/O chậm có ổn không?

**Đáp án:** Phải đo với workload thực, cả match/no-match, allocations và tail latency. Có thể cần pointcut riêng hoặc telemetry sampling, không quyết bằng số nơi reuse.

### Bài 7 — Giữ trạng thái

Một base aspect lưu `lastRequest` cho mỗi concrete child. Có đồng nghĩa mỗi request được cách ly không?

**Đáp án:** Không. Aspect instances có lifecycle riêng; nếu instance shared, field có thể bị nhiều lời gọi dùng chung và giữ request ngoài vòng đời. Dùng local/per-invocation context.

### Bài 8 — Java 17 demo

Vì sao lời gọi `bill-1` có cả BASE và FIN, còn `ship-1` chỉ có BASE?

**Đáp án:** Vì hai Rule cùng khớp prefix `bill-`, nhưng chỉ BASE khớp `ship-1`. Logic `invokeAt` được dùng chung, không tự loại overlap.

### Bài 9 — Lỗi nghiệp vụ

Khi target trong demo ném lỗi `bad`, có được trả `null` để giữ observer “an toàn” không?

**Đáp án:** Không theo contract hiện tại. Observer thuần quan sát phải rethrow lỗi gốc; một fallback là thay đổi semantics và phải được thiết kế riêng.

### Bài 10 — Proxy bypass

Demo gọi `target.run("bill-2")` trực tiếp và không có log. Điều này nói gì về việc dùng reusable AOP qua proxy làm guard bắt buộc?

**Đáp án:** Độ phủ chỉ gồm đường **qua proxy**. Không đặt bảo mật bắt buộc duy nhất ở proxy nếu caller có thể tới effect bằng đường khác; cần kiểm soát ranh giới đáng tin.

### Bài 11 — Tại sao không gộp audit và telemetry?

Cả hai phát event, nhưng audit bắt buộc bền vững còn telemetry cho phép drop. Có nên có một `emit(event)` dùng chung?

**Đáp án:** Có thể dùng chung serializer an toàn nếu contract giống, nhưng **không gộp chính sách delivery/failure**. Nhầm lẫn có thể gây mất audit hoặc làm giao dịch không cần thiết thất bại.

### Bài 12 — Khi nào xóa một abstraction?

Mỗi lần thêm domain lại phải thêm một flag, một thứ tự đặc biệt và nhiều exception handlers riêng. Tái sử dụng còn hiệu quả không?

**Đáp án:** Đây là dấu hiệu trừu tượng sai. Đo chi phí thay đổi và rủi ro rồi cân nhắc tách thành policy riêng, helper thuần hoặc coordinator cho những tương tác bắt buộc.

## 23. Checklist trước khi chốt

1. Các điểm dùng chung có **cùng bất biến** hay chỉ giống cú pháp?
2. Tập join point đã có **positive/negative coverage test** chưa?
3. Cơ chế AOP hỗ trợ đúng loại method call/execution/field/constructor cần áp chưa?
4. Có state nào bị chia sẻ giữa thread/target/request ngoài ý muốn không?
5. Nếu hai aspects cùng khớp, **order và số lần target chạy** có được kiểm chứng?
6. Nếu aspect lỗi, chính sách **fail-open/fail-closed** đúng chức năng chứ?
7. Nếu target lỗi, original result/exception có được bảo toàn?
8. Logic nào đáng đặt ở **helper**, logic nào cần **aspect**, logic nào phải ở **domain coordinator**?
9. Để thêm một domain mới, cần sửa bao nhiêu files/configs/tests?
10. Tác động lên **latency, memory, GC, throughput** đã được đo tại hot path?
11. Khi dependency hoặc compiler/weaver đổi version, có artifact-level test không?
12. Có đường **direct target/self-invocation/async** bypass chính sách không?
13. Có tiêu chí định lượng/định tính để biết khi nào phải tách abstraction?
14. Tài liệu có nêu rõ **những ngữ nghĩa không được tái sử dụng** không?

## 24. Ghi nhớ

- **Tái sử dụng tốt là tái sử dụng một hợp đồng đúng**, không phải tối thiểu số dòng code.
- Trong AOP, **pointcut precision, advice precedence, flow semantics, state lifetime và weaving coverage** là những chi phí thiết kế quan trọng.
- Dùng **helper hoặc strategy** khi chỉ cần chia sẻ thuật toán; dùng **aspect/interceptor** khi có concern thật sự cắt ngang; dùng **coordinator** cho bất biến nghiệp vụ chặt.
- **Abstract aspect** đáng giá khi ngôn ngữ hỗ trợ và các concrete specializations chia sẻ skeleton rõ, không phải mọi mối quan tâm đều nên kế thừa nhau.
- Đừng gộp telemetry, authorization, retry và durable audit chỉ vì chúng đều có `proceed`.
- Một thay đổi dùng chung có thể **giảm lỗi lặp**, đồng thời tăng **blast radius**; cần test, ownership và rollout phù hợp.
- Ra quyết định bằng **chi phí vòng đời, phạm vi đúng, khả năng kiểm thử, độ dễ hiểu và các phép đo thực**, không bằng số lượng classes hay LOC.
- Nếu abstraction ngày càng nhiều flags, exceptions, precedence rules và đường bypass, hãy **đánh giá lại và tách** thay vì tiếp tục đầu tư theo thói quen.
