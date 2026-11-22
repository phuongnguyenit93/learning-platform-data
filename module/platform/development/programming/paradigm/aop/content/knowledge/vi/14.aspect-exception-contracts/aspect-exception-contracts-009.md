# Ghi nhận hợp đồng của aspect cho bên sử dụng trong AOP

## 1. Vì sao một aspect cần hợp đồng dành cho người sử dụng?

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** đóng gói logic xuyên suốt như kiểm toán, xác thực quyền, đo thời gian, kiểm tra bất biến, retry, ghi log hoặc dịch ngoại lệ. **Pointcut** xác định những **join point** thuộc phạm vi cơ chế AOP; **advice** thực hiện hành vi tại các điểm được chọn.

Nếu một thư viện chứa method `publish(String,String)`, người gọi thường đọc chữ ký, Javadoc và kiểu ngoại lệ để biết mình có thể mong đợi điều gì. Nhưng khi AOP tham gia, **hành vi mà người gọi quan sát không chỉ do thân phương thức quyết định**:

- Một before advice có thể từ chối input trước khi thân method chạy.
- Một around advice có thể không gọi tiếp, thay tham số, trả fallback hoặc thực hiện retry.
- Một after-returning advice có thể kiểm tra, ghi audit hoặc vô tình gây lỗi sau khi method gốc đã thành công.
- Một after-throwing advice có thể ghi nhận, chuyển đổi hoặc lan truyền lỗi.
- Nhiều aspect có thể cùng tham gia, tạo thứ tự tác động quan trọng.
- Một lời gọi đi trực tiếp vào target có thể bỏ qua proxy-based advice.

Vì vậy, bên sử dụng cần **hợp đồng của hành vi đã kết hợp** (*composed contract*), không chỉ hợp đồng của mã nghiệp vụ ban đầu. “Ghi nhận hợp đồng” nghĩa là mô tả công khai và có thể kiểm chứng: **khi nào aspect có hiệu lực, người dùng phải đáp ứng gì, aspect bảo đảm gì, nó có thể thay đổi điều gì và những giới hạn nào vẫn tồn tại**.

Bài này hướng dẫn xây tài liệu hợp đồng cho AOP **nói chung, từ cơ bản đến nâng cao**; không giả định một framework, compiler, proxy manager hoặc DSL cụ thể.

## 2. Phân biệt hợp đồng nghiệp vụ, hợp đồng aspect và hợp đồng cuối cùng

Có thể xem hệ thống gồm ba lớp:

```text
Caller
  |
  v
Public API + configured aspects
  |
  v
Business operation
```

**Hợp đồng nghiệp vụ (target contract)** mô tả việc `publish` cần đầu vào nào, khi nào ghi dữ liệu và trả giá trị gì.

**Hợp đồng aspect (aspect contract)** mô tả logic được chèn: chính sách chọn điểm, kiểm tra, ghi log, quyền chuyển lỗi, thứ tự, chi phí và yêu cầu về ngữ cảnh.

**Hợp đồng hợp thành (composed/public contract)** mô tả điều caller **thực sự nhìn thấy** sau khi các aspect được áp dụng. Khi các lớp thay input/output hoặc exception, hợp đồng này có thể khác hợp đồng target.

Ví dụ:

```text
Target.publish(id, body):
    Khi thành công, trả receipt:id.

ValidationAspect:
    Từ chối id rỗng trước khi gọi target.

AuditAspect:
    Ghi event ở đường thành công hoặc lỗi.

Public publish contract:
    Nếu id rỗng, ném IllegalArgumentException,
    không thực hiện target.
    Nếu hợp lệ, áp dụng audit ở phạm vi đã khai báo.
    Kết quả thành công là receipt:id.
```

Đoạn trên là mô tả hợp đồng, không phải cú pháp một ngôn ngữ pointcut cụ thể.

### 2.1. Hợp đồng không phải tên advice

Một dòng như “dùng before advice để validate” **không đủ** cho consumer. Nó chưa trả lời method nào được áp dụng, lỗi gì được ném, phương thức gốc có chạy không và behavior khác nhau ra sao giữa môi trường sử dụng proxy và gọi trực tiếp.

### 2.2. Tài liệu aspect cần có hai đối tượng đọc

- **Người gọi/API consumer:** muốn biết input hợp lệ, output, lỗi, side effect, độ trễ và tính nhất quán.
- **Người cấu hình/vận hành:** muốn biết phạm vi weaving, precedence, configuration, đường có thể bypass, cách debug và hậu quả khi disable aspect.

Hai nhóm thông tin nên liên kết nhưng có thể được trình bày trong các mục riêng để tránh bắt consumer hiểu mọi chi tiết implementation.

## 3. Những mục tối thiểu trong hợp đồng aspect

Một bản mô tả hữu ích nên trả lời:

| Nhóm | Câu hỏi cần ghi nhận |
| --- | --- |
| Danh tính | Aspect tên gì, phiên bản nào, chủ sở hữu bảo trì là ai? |
| Mục đích | Nó bảo vệ/quan sát/chuyển đổi hành vi nào? |
| Phạm vi | Những loại join point, class/method, package, metadata nào được chọn? |
| Ranh giới | Compile/load-time weaving, proxy interception hay hình thức khác? |
| Tiền điều kiện | Caller phải cung cấp dữ liệu/ngữ cảnh gì trước lời gọi? |
| Bảo đảm thành công | Khi trả bình thường, kết quả và trạng thái nào được cam kết? |
| Bảo đảm đường lỗi | Loại lỗi nào có thể xuất hiện, được giữ/chuyển đổi thế nào? |
| Side effect | Advice có log, gửi audit, cập nhật cache, retry hay gọi mạng không? |
| Thứ tự | Precedence với các aspect khác; lớp ngoài/trong? |
| Continuation | Around có thể không `proceed`, gọi nhiều lần hay thay args/result không? |
| Bất biến | Tính chất hệ thống nào phải được giữ sau những ranh giới cụ thể? |
| Giới hạn | Lời gọi nào có thể bypass; final/private/static, internal calls, async? |
| Quan sát | Log/event/metric/tracing được sinh ra; quy tắc dữ liệu nhạy cảm? |
| Vận hành | Điều kiện bật/tắt, chi phí, fallback khi phụ trợ lỗi, rollout? |
| Phiên bản | Thay đổi chính sách có ảnh hưởng hợp đồng đã công bố không? |
| Kiểm chứng | Positive/negative/exception tests nào chứng minh các cam kết? |

Không cần đưa mọi chi tiết bytecode vào tài liệu dành cho consumer. Nhưng những giới hạn có thể **thay đổi điều consumer quan sát** phải được ghi nhận rõ.

## 4. Ghi phạm vi áp dụng bằng ngôn ngữ có thể kiểm chứng

Một câu như “aspect tự động áp dụng cho các service” thường quá mơ hồ. Cần định nghĩa:

- **Join-point kind:** method call, method execution, constructor, field access, hoặc loại được engine hỗ trợ.
- **Selection:** chữ ký, kiểu khai báo, modifier, annotation, pattern hoặc metadata.
- **Inclusion:** vùng class/module hoặc tập operation cụ thể.
- **Exclusion:** các class, method hoặc trường hợp không áp dụng.
- **Runtime guards:** tham số, target type, control flow, identity/ngữ cảnh.
- **Coverage boundary:** mã nào đã được weave, instance nào phải đi qua proxy.

Ví dụ mô tả **trung lập công cụ**:

```text
Aspect: DocumentAudit
Scope:
  - method execution của Publication.publish(String,String)
  - chỉ khi invocation được thực thi qua điểm can thiệp đã đăng ký
  - không áp dụng cho Publication.publishedCount()
Runtime condition:
  - áp dụng cho mọi publish invocation đi qua boundary
Non-coverage:
  - caller gọi trực tiếp raw target sẽ không đi qua proxy audit
```

Một số cơ chế weaving trực tiếp vào method body có thể bao phủ các object được tạo bằng `new`, trong khi proxy delegation chỉ nhìn thấy lời gọi qua proxy. **Không được biến giới hạn của một implementation thành quy tắc chung cho tất cả AOP.**

### 4.1. “Các method được chọn” khác “các invocation thực sự đi qua”

Một class có chữ ký khớp pointcut không tự chứng minh advice chạy. Có thể lớp không nằm trong weaving scope, instance được tạo bên ngoài cơ chế proxy, điều kiện runtime sai hoặc một advice ưu tiên cao hơn chặn `proceed`.

Hợp đồng cần nêu cả **quy tắc matching** và **đường thực thi được bảo đảm**.

### 4.2. Lời gọi nội bộ và self-invocation

Trong mẫu **interface proxy ủy quyền vào target riêng**, `target.outer()` gọi `this.inner()` thường không đi qua proxy, dù `inner()` tự nó là method hợp lệ theo pointcut. Subclass proxy hoặc bytecode weaving có thể có hành vi khác.

Khi tài liệu nói “áp dụng cho mọi invocation”, phải kiểm chứng được self-invocation và các đường khác; nếu không, hãy giới hạn lời cam kết.

## 5. Ghi điều kiện trước của aspect

**Precondition** xác định điều bên gọi phải thỏa để nhận được bảo đảm thành công. Ví dụ:

```text
publish(id, content)
Precondition:
  id != null
  id.isBlank() == false
  content != null
  content.isBlank() == false
```

Nếu aspect được thiết kế để kiểm tra precondition, tài liệu phải nói rõ:

1. Việc kiểm tra nằm **trước hay sau** chuẩn hóa dữ liệu.
2. Loại lỗi/violation khi điều kiện sai.
3. Target có bị gọi hay không khi bị từ chối.
4. Có ghi audit cho request bị từ chối không.
5. Có thông tin nhạy cảm bị đưa vào thông báo lỗi/log không.
6. Caller có được phép sửa input và thử lại không.
7. Điều kiện có áp dụng nhất quán trên mọi entry point không.

### 5.1. Không tự siết chặt public contract

Giả sử public API trước đây cho phép id chứa khoảng trắng rồi tự trim, nay aspect mới từ chối mọi chuỗi có khoảng trắng. Consumer hợp lệ trước đây có thể bị hỏng.

Điều kiện trước quá mạnh có thể vi phạm nguyên tắc thay thế (*behavioral substitutability*) và là **thay đổi hợp đồng API**, dù chữ ký method không đổi.

### 5.2. Validation khác authorization

Input có đúng định dạng **không đồng nghĩa** người gọi có quyền thực hiện operation. Authorization phụ thuộc actor, resource và policy có thể thay đổi theo thời gian.

Nếu một aspect kiểm quyền, contract phải nêu boundary tin cậy, điều gì xảy ra khi không thể xác minh quyền, và việc gọi trực tiếp target có vượt qua kiểm tra không. Với invariant bảo mật cốt lõi, không được chỉ dựa vào một proxy có đường bypass.

## 6. Ghi điều kiện sau: kết quả và trạng thái được bảo đảm

Một **postcondition** có thể liên hệ kết quả với input và trạng thái trước lời gọi:

```text
normal_post(id, oldCount, result, newCount):
  result == "receipt:" + id
  newCount == oldCount + 1
```

Nếu aspect chỉ logging, một contract phù hợp thường là **không sửa** return value hoặc domain state. Nếu aspect làm result transformation, contract phải công bố cách transform.

### 6.1. Kết quả nội bộ và kết quả bên ngoài có thể khác

```text
Target returns internalOrderId
  -> RedactionAdvice returns maskedId
  -> Caller sees maskedId
```

Postcondition target liên quan `internalOrderId`; postcondition public liên quan `maskedId`. Tài liệu của aspect cần ghi chính sách che dữ liệu và giới hạn thông tin, không đơn giản nói “kết quả trả về giống target”.

### 6.2. Side effect đã thực hiện trước khi trả về

Nếu after advice ném exception sau khi target đã ghi dữ liệu, caller có thể nhận lỗi dù trạng thái đã thay đổi. Contract phải chỉ ra **exception có bảo đảm hoàn tác hay không**. Không có rollback tự động chỉ vì advice phát hiện lỗi hậu điều kiện.

### 6.3. Không thể bảo đảm trạng thái trong mọi môi trường đồng thời

Nếu một postcondition đọc `newCount` sau khi thread khác đã thay đổi cùng đối tượng, kết quả so sánh `oldCount + 1` có thể là false positive. Muốn công bố bảo đảm nhất quán phải mô tả **atomicity, isolation hoặc observation boundary** phù hợp.

## 7. Bất biến: công bố đúng ranh giới chứ không kiểm mọi dòng

Một **invariant** là tính chất phải đúng tại những điểm hợp lệ của vòng đời:

```text
publishedCount >= 0
activeResources <= configuredLimit
closed == true  =>  no further successful writes
```

Bản mô tả cần nói rõ:

- Bất biến áp dụng cho từng object, một request hay toàn hệ thống?
- Nó phải đúng tại public method entry/exit, sau commit hay sau completion?
- Có trạng thái trung gian được cho phép bên trong implementation không?
- Nếu kiểm tra phát hiện lỗi, object có bị cô lập hoặc đánh dấu không sử dụng tiếp?
- Trong concurrency, snapshot có nhất quán/atomic không?
- Khi exception, invariant nào vẫn phải giữ?

Một method có thể tạm thay đổi nhiều field rồi khôi phục tính nhất quán trước khi return. Weaving vào mọi private helper để kiểm class invariant có thể tạo lỗi giả nếu bất biến chỉ cam kết ở public boundary.

## 8. Ghi hợp đồng khi có ngoại lệ

Hợp đồng đầy đủ **không chỉ nói về đường thành công**. Cần chỉ rõ:

| Nhóm lỗi | Nguồn có thể có | Cam kết cần công bố |
| --- | --- | --- |
| Precondition violation | Checker từ chối input | Target có chạy không, lỗi gì được ném? |
| Authorization failure | Policy trước target | Có side effect bị cấm không, audit thế nào? |
| Business exception | Target ném | Aspect giữ, dịch hay che lỗi? |
| Postcondition violation | Checker sau target phát hiện sai | State đã đổi chưa, caller xử lý thế nào? |
| Audit/metrics failure | Advice phụ trợ ném | Fail-open hay fail-closed? |
| Cleanup failure | Advice finally/dọn tài nguyên | Có thể che lỗi gốc không? |
| Async exceptional completion | Task kết thúc lỗi sau method return | Ai quan sát, trên stage nào? |

### 8.1. Giữ nguyên lỗi hay chuyển đổi?

Có ba lựa chọn thường thấy:

- **Rethrow:** lan truyền nguyên ngoại lệ gốc khi hợp đồng cho phép.
- **Translate:** tạo một lỗi domain/public mới, giữ lỗi gốc trong `cause` phù hợp.
- **Fallback:** chuyển lỗi thành một giá trị bình thường đã được contract mô tả.

Ví dụ mã Java minh họa (không phải chương trình độc lập):

```java
throw new IllegalStateException("operation unavailable", original);
```

Nếu translation bỏ `cause`, chẩn đoán lỗi sẽ khó hơn. Nếu fallback trả kết quả giả thành công cho thao tác chưa hoàn tất, consumer có thể tin sai vào trạng thái hệ thống.

### 8.2. Phân biệt basic và strong exception guarantee

- **Basic guarantee:** sau lỗi, trạng thái vẫn hợp lệ theo bất biến liên quan nhưng có thể đã đổi.
- **Strong guarantee:** nếu thao tác thất bại, trạng thái thuộc phạm vi cam kết được giữ như trước.
- **No-throw guarantee:** thao tác/phase cụ thể được thiết kế không cho exception thoát theo hợp đồng.

Những bảo đảm này **không tự xuất hiện nhờ AOP**. Thư viện, transaction manager hoặc operation phải thực sự hiện thực hành vi đã hứa.

### 8.3. Caller được phép retry khi nào?

Nếu exception đến từ `AuditAdvice.afterReturning` sau khi target đã hoàn thành ghi, retry toàn bộ operation có thể tạo bản ghi trùng. Hợp đồng cần phân loại lỗi **có thể retry** so với **vi phạm hợp đồng/bug** hoặc “trạng thái chưa xác định”.

Một API ghi dữ liệu nên mô tả idempotency key, cách kiểm tra kết quả đã hoàn tất hoặc cơ chế tránh lặp nếu retry là kịch bản hợp lệ.

## 9. Ghi thứ tự khi có nhiều aspect

Nếu hai aspect cùng áp dụng ở một join point, kết quả có thể phụ thuộc thứ tự:

```text
Validation(
    Authorization(
        Transaction(
            Business
        )
    )
)
```

Với nesting trên:

- Validation có cơ hội từ chối trước khi Authorization chạy.
- Authorization có thể từ chối trước khi transaction bắt đầu.
- Transaction có thể tạo một boundary khi Business thực thi.
- Hành vi thoát sẽ diễn ra từ trong ra ngoài theo đường kết quả và phạm vi các finally tương ứng.

Nhưng **không có một thứ tự cụ thể áp dụng cho mọi công cụ AOP**. Mỗi engine có quy tắc precedence và behavior riêng. Hợp đồng consumer nên công bố những thứ tự **ảnh hưởng correctness**; tài liệu kỹ thuật nên chỉ ra cấu hình thực thi và test xác nhận chúng.

### 9.1. Precedence là quyền bao phần tiếp tục

Một around advice ngoài có thể không gọi `proceed`, khiến advice trong và business không chạy. Vì thế “các aspect A, B, C được cấu hình” chưa đủ để bảo đảm tất cả thực thi ở mọi invocation.

### 9.2. Lỗi của advice trong thành lỗi của advice ngoài

Một target có thể return thành công, rồi after advice trong ném exception. Advice ngoài trên nhánh lỗi có thể nhìn lỗi từ **advice trong** chứ không phải lỗi target.

Hợp đồng public cần mô tả đúng đường lỗi mà caller thấy và tránh gắn mọi thrown exception thành “business failed”.

## 10. Ghi rõ quyền của around advice

Trong một số mô hình AOP, around advice có thể:

- **Không gọi continuation** và từ chối yêu cầu.
- **Gọi một lần** để tiếp tục bình thường.
- **Gọi nhiều lần** để retry, nếu DSL/engine cho phép.
- Thay tham số truyền xuống.
- Thay kết quả trả lên.
- Bắt, dịch, nuốt hoặc tạo ngoại lệ.
- Gọi các công việc phụ trước/sau/trong continuation.

Các quyền này phải được mô tả theo **hành vi mà consumer cần dựa vào**, ví dụ:

```text
Aspect: CachedLookup
If cache has a valid entry:
  target is not called
  a cached result satisfying the published staleness limit is returned
Else:
  target is called once
Errors:
  cache failure is treated as miss, unless configured fail-closed
```

Đây là hợp đồng minh họa, không phải lời hứa mặc định của một cơ chế caching AOP nào.

Nếu không biết aspect có quyền gọi lại operation hay không, consumer không thể lập luận về số lần side effect.

## 11. Ghi side effect của aspect

Một aspect có thể trông như “phụ trợ” nhưng vẫn có side effect đáng kể:

- Gửi event audit.
- Ghi log có dữ liệu nhạy cảm.
- Gọi network hoặc storage.
- Tăng counter.
- Ghi cache hoặc invalidate cache.
- Thiết lập/giải phóng transaction context.
- Thay security principal.
- Đặt hoặc xóa thread/request context.
- Thực thi retry hoặc compensation.
- Giữ lock và thay đổi thời gian scheduling.

Mỗi side effect cần ghi:

1. Xảy ra ở phase nào?
2. Là synchronous hay asynchronous?
3. Có bảo đảm **at-most-once**, **at-least-once** hay exactly-once trong phạm vi nào không?
4. Nếu thất bại, caller có nhận lỗi không?
5. Có bị lặp khi retry/reentrancy không?
6. Thông tin nào được lưu, trong bao lâu và ai có quyền truy cập?
7. Có thể làm thay đổi kết quả/ngoại lệ mà caller quan sát không?

**Không nên hứa exactly-once** khi không có bằng chứng thiết kế tương ứng. Ví dụ một log line chỉ cho biết handler được gọi, không chứng minh một event đã được ghi bền vững đúng một lần ở hệ thống từ xa.

## 12. Mô tả khả năng observability mà không hứa quá mức

Một contract observability có thể nói:

```text
At proxy entry:
  emit audit.attempt with operation ID

After normal return:
  emit audit.success

After thrown exception:
  emit audit.failure with error class

On audit sink failure:
  preserve the primary operation outcome when policy is best-effort
```

Nhưng cần xác định:

- “emit” nghĩa là đưa vào bộ đệm hay lưu bền vững?
- Log có thể bị sampling không?
- Log của việc bị từ chối ở before advice được ghi ở đâu?
- Nếu consumer gọi raw target, event có xuất hiện không?
- Một async operation được log “success” khi method return hay khi Future complete?
- Nếu nhiều advice lồng nhau, có một event hay nhiều event cho mỗi attempt?

### 12.1. Correlation và invocation identity

Một method có thể chạy hàng nghìn lần. Chỉ ghi method name không đủ ghép event. Có thể dùng **trace ID**, **invocation/span ID** và **build/config ID** khi phù hợp.

Không nên gán trace ID bằng một shared mutable field cho mọi thread. Đối với callback/async, context cần theo tác vụ và phải được dọn đúng vòng đời.

### 12.2. Bảo vệ dữ liệu nhạy cảm

Không mặc định serialize toàn bộ args/result để “ghi nhận hợp đồng”. Aspect thường nhìn dữ liệu ở ranh giới nhạy cảm trước khi che hoặc mã hóa.

Nên công bố danh sách field được phép log, quy tắc mask/redact, retention và giới hạn quyền truy cập. Log có thể chứa thông tin nhận dạng/ủy quyền, nên dữ liệu chẩn đoán cũng cần hợp đồng bảo mật.

## 13. Hiệu năng và tài nguyên là một phần của hợp đồng vận hành

Một aspect có thể thêm:

- Một dispatcher/proxy hop.
- Reflection hoặc logic binding ngữ cảnh.
- Kiểm tra điều kiện động.
- Cấp phát object/exception/trace context.
- Network round trip để kiểm quyền/audit.
- Lock hoặc thao tác transaction.
- Retry làm tăng số lần gọi target.
- Async callback hoặc queue.

Không phải mọi overhead đều đo được bằng “bao nhiêu nano giây mỗi proxy call”. Contract vận hành có thể công bố:

- Giới hạn timeout và điều gì xảy ra khi timeout.
- Chính sách backpressure/rate limit.
- Cách xử lý khi sink audit không khả dụng.
- Số attempt tối đa khi retry.
- Có khả năng block thread hay không.
- Loại metric chính và phân biệt request với attempt.
- SLO mong muốn nếu có số đo thực tế và một hệ thống cam kết cụ thể.

**Không tự đặt một ngưỡng latency hay exactly-once guarantee nếu chưa đo/thiết kế.** Với tài liệu học tập, chỉ đưa các trường cần được định nghĩa; giá trị số phải xuất phát từ hệ thống được vận hành.

## 14. Tài liệu không nên phụ thuộc vào chi tiết implementation không ổn định

Để consumer dễ sử dụng, mô tả **hợp đồng quan sát được** trước:

```text
Nếu id không hợp lệ:
  publish ném IllegalArgumentException
  target không được gọi thông qua boundary đã quản lý
```

Sau đó mới mô tả **cơ chế hiện thực**:

```text
Một interface proxy kiểm tra đầu vào trước khi ủy quyền cho target.
```

Tách hai tầng giúp thay proxy bằng bytecode weaving hoặc facade mà không buộc phải viết lại mọi mô tả API, miễn behavior thật vẫn tương thích.

Tuy vậy, những chi tiết mechanism có tác động **phạm vi bảo đảm** (như self-invocation bypass) phải được ghi công khai, không giấu dưới nhãn “internal detail”.

## 15. Ví dụ tài liệu hợp đồng cho một aspect kiểm soát publication

Một bản hợp đồng độc lập có thể trình bày:

### 15.1. Danh tính và phạm vi

```text
Aspect ID: publication-contract
Applies to: Publication.publish(String,String)
Boundary: caller -> managed Publication proxy -> target
Excluded: Publication.publishedCount()
Non-covered: calls made directly to raw target
```

### 15.2. Điều kiện trước

```text
id and body must be non-null, nonblank.
On failure:
  IllegalArgumentException
  target.publish is not invoked.
```

### 15.3. Điều kiện sau

```text
For normal completion:
  result == "receipt:" + id
  publishedCount increases by exactly one
```

### 15.4. Khi có lỗi

```text
If target throws:
  original exception is propagated through this proxy boundary.
  No strong rollback guarantee is asserted by this aspect.
  Postcondition for normal completion is not applied.
```

### 15.5. Side effect và khả năng bypass

```text
The aspect prints demonstration events at entry, success,
failure and exit.
This is an educational example, not a durable audit log.
Caller using target directly does not run these checks.
```

**Chú ý:** nội dung trên chỉ mô tả ví dụ Java ngay sau đây. Với một hệ thống production, hợp đồng phải được thay bằng đúng policy, version, failure mode và phạm vi thực tế — không sao chép nguyên mà coi là bảo đảm.

## 16. Ví dụ Java 17 chạy được: hợp đồng được thực thi tại proxy

Ví dụ sử dụng **JDK dynamic proxy**. Nó không phải engine AOP đầy đủ: không phân tích pointcut DSL và không biến đổi bytecode target. Nhưng nó thể hiện rõ **hợp đồng dành cho consumer ở ranh giới proxy**, cách xử lý return/exception và một đường bypass có thể kiểm chứng.

Tạo file `AspectConsumerContractDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AspectConsumerContractDemo {

    interface Publication {
        String publish(String id, String body);
        int publishedCount();
    }

    static final class Repository implements Publication {
        private int count;

        @Override
        public String publish(String id, String body) {
            System.out.println("business:publish:" + id + ":" + body);
            if ("FAIL".equals(body)) {
                throw new IllegalStateException("repository unavailable");
            }
            count++;
            return "receipt:" + id;
        }

        @Override
        public int publishedCount() {
            return count;
        }
    }

    static Publication withContract(Repository target) {
        return (Publication) Proxy.newProxyInstance(
                Publication.class.getClassLoader(),
                new Class<?>[] { Publication.class },
                (Object proxy, Method method, Object[] args) -> {
                    if (!method.getName().equals("publish")) {
                        return method.invoke(target, args);
                    }

                    System.out.println("contract:enter:publish");
                    try {
                        String id = (String) args[0];
                        String body = (String) args[1];
                        if (id == null || id.isBlank()) {
                            throw new IllegalArgumentException("id required");
                        }
                        if (body == null || body.isBlank()) {
                            throw new IllegalArgumentException("body required");
                        }

                        int old = target.publishedCount();
                        String result;
                        try {
                            result = (String) method.invoke(target, args);
                        } catch (InvocationTargetException wrapped) {
                            Throwable original = wrapped.getCause();
                            System.out.println("contract:failure:"
                                    + original.getClass().getSimpleName());
                            if (target.publishedCount() < 0) {
                                throw new IllegalStateException(
                                        "invariant violated", original);
                            }
                            throw original;
                        }

                        if (!result.equals("receipt:" + id)
                                || target.publishedCount() != old + 1) {
                            throw new IllegalStateException(
                                    "postcondition violated");
                        }

                        System.out.println("contract:success:" + result);
                        return result;
                    } finally {
                        System.out.println("contract:exit:publish");
                    }
                }
        );
    }

    static void tryPublish(String label, Publication p,
                           String id, String body) {
        System.out.println("case:" + label);
        try {
            System.out.println("caller:" + p.publish(id, body));
        } catch (RuntimeException error) {
            System.out.println("caller:error:"
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage());
        }
    }

    public static void main(String[] args) {
        Repository target = new Repository();
        Publication managed = withContract(target);

        tryPublish("ok", managed, "D1", "hello");
        tryPublish("invalid", managed, " ", "hello");
        tryPublish("failure", managed, "D2", "FAIL");
        tryPublish("bypass", target, "D3", "direct");

        System.out.println("caller:count:" + managed.publishedCount());
        System.out.println("caller:same-reference:" + (managed == target));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AspectConsumerContractDemo.java
java AspectConsumerContractDemo
```

**Đầu ra dự kiến:**

```text
case:ok
contract:enter:publish
business:publish:D1:hello
contract:success:receipt:D1
contract:exit:publish
caller:receipt:D1
case:invalid
contract:enter:publish
contract:exit:publish
caller:error:IllegalArgumentException:id required
case:failure
contract:enter:publish
business:publish:D2:FAIL
contract:failure:IllegalStateException
contract:exit:publish
caller:error:IllegalStateException:repository unavailable
case:bypass
business:publish:D3:direct
caller:receipt:D3
caller:count:2
caller:same-reference:false
```

### 16.1. Trường hợp thành công

`managed.publish("D1","hello")` đi qua handler:

1. Ghi sự kiện `enter`.
2. Kiểm tra precondition.
3. Lưu `oldCount`.
4. Ủy quyền tới target; target tăng counter và trả receipt.
5. Kiểm postcondition `receipt:D1` và count tăng đúng một.
6. Ghi `success`, chạy `finally` và trả giá trị tới caller.

### 16.2. Trường hợp input sai

`id = " "` làm `isBlank() == true`; handler ném `IllegalArgumentException("id required")` **trước khi gọi target**. Do khối `finally` đã được vào, dòng `contract:exit` vẫn xuất hiện.

Contract nói chính xác **target không được gọi khi precondition không hợp lệ**. Có thể kiểm bằng counter hoặc absence of business event, không chỉ assert loại lỗi.

### 16.3. Trường hợp target ném lỗi

`body = "FAIL"` làm target ném `IllegalStateException`. Reflection chuyển lỗi sang `InvocationTargetException`; handler lấy `getCause()` rồi ném lại exception gốc. Nó không chạy normal postcondition.

Checker exceptional ở ví dụ chỉ kiểm count không âm; nó **không khẳng định strong rollback guarantee** cho tất cả trường hợp lỗi. Nếu target có thể thay đổi state trước khi ném, tài liệu phải mô tả điều đó hoặc có cơ chế hoàn tác thực sự.

### 16.4. Trường hợp bypass

`tryPublish("bypass", target, ...)` gọi **thẳng target**. Đường này **không có bất kỳ dòng `contract:*` nào**, mặc dù target có cùng interface và method. Đây là giới hạn của interface proxy delegation trong ví dụ.

Khi contract được xem là bảo vệ bắt buộc, ứng dụng phải thiết kế sao cho consumer có trách nhiệm không lấy raw target hoặc áp dụng bảo vệ ở ranh giới không thể bypass.

### 16.5. Những điều ví dụ không chứng minh

- Không tự tạo pointcut parser, join point shadow hoặc weaving compiler.
- Không chặn mọi internal call, constructor, static field/method hoặc bytecode.
- Không bảo đảm an toàn đồng thời cho counter trong multi-threading.
- Không cung cấp transaction, rollback, durable audit hay exactly-once semantics.
- Không thay thế một API contract riêng cho production.
- Không nói rằng một công cụ AOP khác chắc chắn có cùng thứ tự advice.

Mục đích của ví dụ là làm **hợp đồng cụ thể, quan sát được và có kiểm thử**, chứ không mô phỏng mọi chức năng AOP.

## 17. Cách đưa hợp đồng vào tài liệu của API

Một consumer thường không mở file cấu hình weaving để đọc trước mỗi lời gọi. Tài liệu phù hợp có thể gồm:

1. **API documentation**: ở nơi mô tả phương thức/operation công khai.
2. **Aspect contract document**: một trang theo danh tính/chính sách aspect.
3. **Configuration reference**: phạm vi, precedence, các switch/option.
4. **Release notes**: mọi thay đổi behavior từ phiên bản trước.
5. **Architecture decision record**: tại sao chọn interception boundary, giới hạn và lựa chọn thay thế.
6. **Test suite**: các lời cam kết quan trọng được xác nhận tự động.

Nếu dùng Javadoc, có thể ghi thông tin consumer quan trọng trực tiếp trên interface:

```java
/**
 * Công bố tài liệu.
 *
 * <p>Trong cấu hình API có contract interceptor:
 * id và body phải có nội dung; đầu vào sai bị từ chối
 * trước khi gọi target.
 *
 * <p>Khi kết thúc bình thường, trả "receipt:" + id.
 * Khi thất bại, xem exceptional guarantee được công bố
 * cho operation; không mặc định có rollback.
 */
String publish(String id, String body);
```

Đây là **mảnh Javadoc minh họa**, không phải class độc lập. Tài liệu cần phân biệt hợp đồng **luôn áp dụng của API** với hợp đồng **chỉ áp dụng trong cấu hình có interceptor**, tránh làm consumer hiểu sai khi dùng implementation thô.

### 17.1. Ghi phiên bản của hợp đồng, không chỉ phiên bản mã

Cấu hình pointcut hoặc thứ tự advice có thể thay đổi behavior mà không sửa public method signature. Do đó release notes nên nêu:

- Method nào mới thuộc phạm vi can thiệp?
- Method nào bị loại khỏi chính sách?
- Precondition có mạnh hơn/yếu đi không?
- Return value hoặc exception taxonomy có đổi không?
- Retry/timeout/audit guarantees có đổi không?
- Có thay đổi từ best-effort sang fail-closed hoặc ngược lại không?
- Có thay đổi đường bypass và yêu cầu cách khởi tạo object không?

Một thay đổi chỉ ở config **vẫn có thể là breaking change** đối với consumer.

## 18. Mẫu Markdown hợp đồng aspect tái sử dụng

Mẫu dưới đây dùng các trường **cần điền bằng thông tin thật của hệ thống**; đây không phải cấu hình chạy được:

```markdown
# Aspect Contract: <Tên chính sách>

## Identity
- Contract version:
- Owner:
- Purpose:

## Applicability
- Join point kinds:
- Included operations:
- Excluded operations:
- Weaving/proxy boundary:
- Dynamic guards:
- Known bypass paths:

## Caller obligations
- Input preconditions:
- Required context:
- Concurrency/identity assumptions:

## Normal guarantees
- Return value:
- State postcondition:
- Invariants:
- Side effects:

## Exceptional guarantees
- Expected exception classes:
- Wrapping/translation:
- Basic or strong guarantee:
- Retry/idempotency guidance:
- Cleanup/audit failure policy:

## Interaction
- Ordering/precedence:
- Short-circuit/fallback behavior:
- Maximum invocation count:
- Async completion boundary:

## Operations
- Enable/disable behavior:
- Timeout/failure mode:
- Logs/metrics/tracing:
- Sensitive data handling:

## Compatibility and verification
- Breaking changes:
- Consumer migration:
- Positive and negative tests:
- Evidence of interception coverage:
```

**Chú ý:** `<Tên chính sách>` trong mẫu là placeholder **cho người áp dụng template**, không phải một phần của bài Java chạy được. Với artifact sản xuất, phải thay các trường này bằng giá trị/những câu cam kết thật trước khi công bố. Đừng để một trường trống được hiểu thành bảo đảm mặc định.

### 18.1. Mẫu hợp đồng là một phần của quy trình review

Nên để cả người sở hữu business API và người sở hữu aspect cùng review. Bên cung cấp aspect biết implementation; bên sở hữu API biết semantic contract mà consumer phụ thuộc. Một phía tự viết không kiểm soát đầy đủ thay đổi trên đường call cuối.

## 19. Cách diễn đạt quyền và nghĩa vụ sao cho không mơ hồ

So sánh:

**Mơ hồ:**

> Aspect sẽ xử lý exception phù hợp.

**Có thể kiểm chứng:**

> Khi `publish` qua managed proxy ném `IllegalStateException` từ target, interceptor ghi sự kiện failure và lan truyền cùng loại exception; không trả fallback.

**Mơ hồ:**

> Aspect chạy với tất cả service.

**Có thể kiểm chứng:**

> Chỉ những invocation của `Publication.publish(String,String)` đi qua `Publication` proxy được cấp bởi factory mới nhận các kiểm tra hợp đồng trong phiên bản này.

**Mơ hồ:**

> Aspect không ảnh hưởng nghiệp vụ.

**Có thể kiểm chứng:**

> Aspect chỉ ghi event và đo thời lượng; với sink best-effort, lỗi gửi metric không được thay return/exception của target và không làm target chạy thêm lần nào.

Một phát biểu càng cụ thể, càng dễ biến thành test. Khi chưa có bảo đảm, nên ghi **“không cam kết”** thay vì viết một câu chung gây cảm giác an toàn giả.

## 20. Phân biệt lỗi caller, lỗi implementation và lỗi của aspect

Trong Design by Contract:

- Vi phạm **precondition** có thể chỉ ra caller cung cấp dữ liệu/ngữ cảnh không hợp lệ.
- Vi phạm **normal postcondition** với precondition đúng có thể chỉ ra implementation hoặc advice biến đổi kết quả sai.
- Vi phạm **invariant** có thể liên quan lifecycle, concurrency hoặc bug state management.
- Lỗi **advice** có thể do audit sink, logger, timeout, cache hoặc exception translation.

Nếu mọi thứ đều trở thành một `RuntimeException("AOP failed")`, consumer khó quyết định có retry hay không.

Nên công bố taxonomy lỗi ổn định ở mức API, giữ `cause` cho chẩn đoán khi phù hợp và tránh để lỗi phụ trợ che lỗi chính ngoài ý định.

### 20.1. Checked và unchecked exceptions trong Java

Với JDK dynamic proxy, một checked exception do `InvocationHandler` ném nhưng **không tương thích với `throws` của method interface** có thể bị runtime bọc trong `UndeclaredThrowableException`. Vì thế contract phải tương thích với chữ ký public API, không mặc định rằng mọi lỗi từ target sẽ luôn xuất hiện nguyên dạng.

Ví dụ chương trình trên chủ yếu dùng unchecked exceptions, tránh tình huống checked exception ngoài chữ ký. Khi xây API thật, phải kiểm tra đường chuyển tiếp lỗi theo interface và engine cụ thể.

## 21. Thứ tự và tương thích khi nhiều aspect được thêm hoặc bỏ

Một aspect mới có thể biến API cũ thành API khác về hành vi, dù target không đổi.

Ví dụ:

```text
Before change:
  Caller -> Target

After change:
  Caller -> Retry -> Audit -> Target
```

Khả năng thay đổi:

- Target có thể được gọi nhiều lần do retry.
- Audit có thể ghi một event mỗi attempt thay vì mỗi request.
- Caller có thể thấy thời lượng lớn hơn.
- Một exception có thể được chuyển thành fallback.
- Thứ tự log có thể khác.
- Side effect có thể lặp khi operation không idempotent.

Bản ghi hợp đồng nên ghi rõ **số lần thực thi tối đa của operation**, nếu số lần có ý nghĩa. Nếu không biết chắc, không hứa “gọi đúng một lần”.

### 21.1. Kiểm tra backward compatibility

Một thay đổi có thể là breaking change khi:

- Thắt chặt precondition.
- Làm yếu bảo đảm postcondition.
- Bỏ một loại lời gọi khỏi interception.
- Đổi fail-open thành fail-closed hoặc ngược lại.
- Thay quy tắc audit/durable logging mà consumer/vận hành dựa vào.
- Thêm retry vào operation có side effect không idempotent.
- Đổi loại exception public.
- Đổi thời điểm success của async task.
- Bắt consumer sử dụng proxy factory thay vì direct construction.

Đánh giá tương thích **theo hành vi bên ngoài**, không chỉ theo compile-time API.

## 22. Contract với thao tác bất đồng bộ

Một method có thể trả `CompletableFuture<Receipt>`. Hợp đồng phải tách:

1. **Method-return contract:** trả một Future hợp lệ, đăng ký công việc đúng cách.
2. **Completion contract:** nếu Future hoàn tất bình thường, Receipt đáp ứng postcondition; nếu exceptional, lỗi và state thỏa exceptional guarantee.
3. **Cancellation/timeout contract:** cancel có ngăn side effect chưa chạy không, hay chỉ dừng chờ?
4. **Context contract:** trace/actor/transaction context được chuyển và xóa như thế nào?

Một after-returning advice ở method execution thường chỉ nhìn việc **trả Future**, không tự chứng minh task đã hoàn tất. Nếu consumer nhận tài liệu “after success đã kiểm” mà checker chỉ chạy khi Future được tạo, đó là mô tả gây hiểu nhầm.

### 22.1. Đừng hứa callback order khi không có ràng buộc

Hai callback async được đăng ký theo thứ tự A rồi B không đương nhiên thực thi theo A rồi B trong mọi scheduler/API. Nếu contract yêu cầu ordering, phải dùng cơ chế sequencing phù hợp và kiểm thử trên môi trường đích.

## 23. Contract khi có đồng thời, đệ quy và reentrancy

Một interceptor có thể được dùng đồng thời bởi nhiều thread. Nếu nó lưu `currentRequestId` trong một field mutable chung mà không quản lý scope, event của hai invocation có thể gắn sai request.

Cần ghi nhận:

- Handler/advice có thread-safe không?
- State nào là singleton, state nào per invocation?
- Có lock hay không; lock order, nguy cơ deadlock?
- Một operation có thể gọi lại chính nó không?
- Advice có thể tự kích hoạt vì logger/cache/client cũng khớp pointcut không?
- Một invocation có thể được thực hiện lại bởi retry?
- Có bảo đảm snapshot/invariant atomic hay chỉ best-effort monitoring?

Một contract “thread-safe” chỉ nên công bố khi implementation được thiết kế và kiểm thử tương ứng. AOP weaving hoặc dynamic proxy **không tự tạo thread safety** cho target.

### 23.1. Tránh vòng lặp interception

```text
AuditAdvice
   -> auditLogger.log()
       -> cùng pointcut
           -> AuditAdvice ...
```

Nếu logger cũng bị can thiệp, có thể xảy ra recursion hoặc số lần advice tăng bất thường. Tài liệu kỹ thuật cần nêu exclusion và chính sách reentrancy; consumer cần biết những thay đổi observability/performance có thể quan sát được.

## 24. Contract của việc bật, tắt và đổi cấu hình

Một aspect đôi khi được bật theo profile, feature flag hoặc module deployment. Ghi hợp đồng cần tránh tuyên bố behavior “luôn có” khi có thể bị tắt ở runtime.

Cần phân biệt:

- **Public invariant không thể vô hiệu hóa:** ví dụ giới hạn dữ liệu bắt buộc.
- **Policy tùy cấu hình:** logging/metrics/tracing hoặc kiểm thử nâng cao.
- **Fail-open/fail-closed:** kết quả khi dependency của aspect không khả dụng.
- **Hot reload:** thay đổi cấu hình có áp cho invocation đang chạy hay chỉ invocation mới?
- **Rollout/rollback:** làm sao biết request nào đã đi qua chính sách phiên bản nào?
- **Consistency:** cùng một request đi qua nhiều instance có thể gặp config khác nhau không?

Nếu một bảo đảm nghiệp vụ chỉ được thực thi bởi advice mà có thể tắt, consumer **không nên được hứa** bảo đảm tuyệt đối mà không nêu điều kiện.

### 24.1. Khả năng kiểm toán cấu hình

Nên có version/build/config ID để liên kết event runtime và tài liệu contract đang có hiệu lực. Một lần chạy có thể dùng artifact cũ hoặc một class đã được nạp trước khi weaving được kích hoạt; không chỉ nhìn source hiện tại để suy ra hành vi production.

## 25. Đưa hợp đồng vào kiểm thử tự động

Một bảng tiêu chí:

| Tình huống | Điều consumer phải nhận thấy |
| --- | --- |
| Input hợp lệ, method được quản lý | Advice phù hợp chạy; target chạy đúng số lần cam kết |
| Input vi phạm precondition | Lỗi công bố; target không chạy nếu policy hứa vậy |
| Normal return | Kết quả và trạng thái đáp ứng public postcondition |
| Target ném lỗi | Lỗi được giữ/translate theo contract |
| Advice sau target ném lỗi | Không gán nhãn sai thành lỗi business; side effect được ghi nhận |
| Around trả fallback | Giá trị fallback có hợp đồng riêng, không giả success |
| Around không proceed | Target/inner advice không chạy như tài liệu |
| Retry | Số attempt, lỗi được phép retry, idempotency đúng |
| Không khớp pointcut | Không có advice ngoài phạm vi |
| Direct target call | Được nhận diện là bypass nếu cơ chế proxy |
| Self-invocation | Đúng phạm vi loại proxy/weaving thật |
| Concurrent invocations | Không trộn context, state và correlation |
| Future completion | Không nhầm method return với task completion |
| Audit sink lỗi | Fail-open/fail-closed đúng cam kết |
| Disable policy | Behavior phù hợp contract của chế độ disabled |
| Upgrade aspect | Kiểm tra breaking changes về scope/exception/result |

### 25.1. Kiểm chứng contract bằng sự kiện chứ không chỉ bằng return value

Khi target trả đúng result ở cả direct call và proxy call, chỉ assert result sẽ bỏ sót việc aspect không chạy. Có thể dùng event collector/counter trong test để xác nhận:

- `before` chạy bao nhiêu lần?
- `afterReturning`/`afterThrowing` chạy ở nhánh nào?
- Target đã thực thi hay chưa?
- Snapshot pre/post được lấy đúng invocation không?
- Advice có chạy cho một method nằm ngoài phạm vi không?

### 25.2. Test với môi trường đúng ranh giới

Một unit test tạo target bằng `new` không giống integration test nhận managed proxy. Khi contract yêu cầu interception, test setup phải mô phỏng **đường cấp phát/reference và cấu hình thực tế**; đồng thời có negative test cho bypass.

## 26. Những lỗi ghi tài liệu thường gặp

**“Aspect chạy trước mọi method.”** Quá rộng, không có giới hạn join point, scope, guard và bypass.

**“Đã chạy audit nghĩa là event đã được lưu vĩnh viễn.”** Không chắc nếu chỉ đưa vào queue hoặc buffer.

**“Khi lỗi, thao tác không thực hiện.”** Có thể sai nếu lỗi phát sinh sau side effect hoặc khi commit trạng thái đã mơ hồ.

**“Các aspect đều trong suốt.”** Sai khi có short-circuit, retry, result translation, security rejection hoặc exception masking.

**“Kết quả luôn giống target.”** Không đúng nếu có advice thay result hoặc trả fallback.

**“Chữ ký không đổi nên hợp đồng không đổi.”** Không đúng nếu pointcut, precedence hoặc configuration đổi.

**“Proxy bảo vệ toàn bộ class.”** Không nếu caller gọi raw target hoặc self-invocation không đi qua interceptor.

**“After returning nghĩa tác vụ async thành công.”** Có thể chỉ là method trả Future.

**“Lỗi logging không bao giờ ảnh hưởng business.”** Chỉ đúng nếu implementation/failure policy thật sự bảo đảm điều đó.

**“ContractViolation luôn nghĩa caller sai.”** Vi phạm postcondition hoặc invariant có thể là lỗi implementation/advice.

**“Có exception là state sẽ rollback.”** Không; rollback cần một cơ chế và phạm vi bảo đảm thực tế.

**“Đã có doc là không cần test.”** Không; contract là lời hứa, test và vận hành là chứng cứ thực hiện.

## 27. Câu hỏi tự luyện

### 27.1. Pointcut đúng nhưng advice không chạy

Một `Publication.publish` có chữ ký khớp, nhưng caller dùng `new Repository()` và gọi trực tiếp. Tài liệu nào cần bổ sung?

**Đáp án:** Ranh giới interception và đường bypass. Nếu chính sách chỉ áp qua proxy, phải công bố rằng caller cần dùng managed proxy/factory để nhận bảo đảm.

### 27.2. Audit lỗi sau khi business thành công

Target đã ghi dữ liệu, after advice audit ném lỗi. Caller nhận exception. Có thể công bố “không có dữ liệu được ghi khi exception” không?

**Đáp án:** Không nếu không có strong guarantee thật sự bao cả trường hợp ấy. Cần mô tả side effect đã có thể xảy ra và chiến lược kiểm tra trạng thái/retry.

### 27.3. Siết precondition

API trước đây chấp nhận chuỗi id có khoảng trắng, sau khi thêm checker chỉ cho chuỗi đã trim. Có phải thay đổi backward compatible?

**Đáp án:** Không nhất thiết; có thể là breaking behavioral change vì caller hợp lệ trước đây bị từ chối.

### 27.4. Retry và number of invocations

Around advice thử lại tối đa ba lần. Có thể viết “target được gọi đúng một lần” trong contract không?

**Đáp án:** Không. Phải ghi số attempt tối đa và điều kiện retry, đặc biệt khi target có side effect.

### 27.5. Exception translation

Target ném `IOException` nhưng aspect public hóa `DomainUnavailable`. Consumer cần biết gì?

**Đáp án:** Loại exception public, dữ liệu/cause có được giữ không, trạng thái sau lỗi và quy tắc retry/cancellation.

### 27.6. Future completion

Method trả `CompletableFuture`; after returning advice ghi “success”. Có bảo đảm operation hoàn tất thành công chưa?

**Đáp án:** Không. Cần hợp đồng completion riêng và giám sát stage/task thực.

### 27.7. Bất biến giữa nhiều aspect

Một aspect trong sửa state rồi aspect ngoài sửa result. Checker đặt trong cùng một method body chỉ kiểm state ban đầu. Có đủ chứng minh public contract không?

**Đáp án:** Không. Phải kiểm composed contract ở đúng boundary và có kiểm tra riêng cho side effect/invariant cần giữ.

### 27.8. Tắt checker

Một cấu hình cho phép disable contract aspect trong production. Có được ghi “mọi lời gọi luôn được validate bởi aspect” không?

**Đáp án:** Không. Phải nêu điều kiện bật/tắt hoặc đặt validation bắt buộc tại boundary không bị vô hiệu hóa.

### 27.9. Concurrent state

Hai thread sửa counter khi checker đang lấy `old` và `new`. Một phép so sánh sai có đủ chứng minh bug nghiệp vụ không?

**Đáp án:** Chưa. Contract phải chỉ rõ tính nhất quán/atomicity của snapshot và phép biến đổi.

### 27.10. Tính trong suốt

Aspect chỉ ghi metric nhưng thỉnh thoảng tự ném exception do sink không khả dụng. Có còn đạt hợp đồng “không ảnh hưởng kết quả nghiệp vụ” không?

**Đáp án:** Không nếu exception phụ trợ thoát tới caller thay vì được xử lý theo best-effort policy được công bố.

## 28. Checklist công bố hợp đồng cho consumer

- [ ] Có tên, version, owner và mục đích aspect.
- [ ] Nêu rõ join point kind, inclusion/exclusion và runtime guard.
- [ ] Nêu rõ weaving/proxy boundary và các đường bypass.
- [ ] Phân biệt hợp đồng target, aspect và composed/public API.
- [ ] Viết precondition theo input và ngữ cảnh caller quan sát.
- [ ] Nêu rõ cách từ chối, error type và việc target có được gọi không.
- [ ] Viết normal postcondition có thể kiểm chứng.
- [ ] Viết exceptional guarantee riêng, không hứa rollback mặc định.
- [ ] Nêu invariant và thời điểm nó phải đúng.
- [ ] Ghi rõ aspect có sửa args/result/error hay không.
- [ ] Ghi rõ quanh-advice có short-circuit, retry hoặc fallback không.
- [ ] Ghi precedence của những aspect có phụ thuộc.
- [ ] Ghi loại side effect và semantics thất bại của chúng.
- [ ] Phân biệt audit/log “đã gửi” với “đã lưu bền vững”.
- [ ] Có chính sách bảo vệ dữ liệu nhạy cảm trong trace/log.
- [ ] Phân biệt method return với completion bất đồng bộ.
- [ ] Nêu các bảo đảm concurrency/reentrancy thực sự có.
- [ ] Ghi cấu hình bật/tắt, fail-open/fail-closed và giới hạn vận hành.
- [ ] Có kiểm thử positive, negative, bypass, error, retry và multi-aspect.
- [ ] Có release notes cho mọi thay đổi behavior có thể ảnh hưởng consumer.
- [ ] Không hứa số liệu hiệu năng chưa được đo.
- [ ] Kiểm tra chữ ký `throws` và exception wrapping với proxy Java.
- [ ] Có bằng chứng trên đường gọi thật, không chỉ pointcut matching tĩnh.
- [ ] Không chỉ dựa vào tài liệu để bảo vệ chính sách bảo mật bắt buộc.
- [ ] Consumer có thể tìm đúng contract version áp dụng trong môi trường của mình.

## 29. Kết luận

**Ghi nhận hợp đồng của aspect cho bên sử dụng** là công bố hành vi của **toàn bộ đường thực thi được kết hợp**, bao gồm những gì caller phải đáp ứng, những gì hệ thống bảo đảm, những thay đổi do advice gây ra, và các giới hạn của phạm vi can thiệp.

Tài liệu tốt không dừng ở “aspect này dùng để logging” hoặc “pointcut chọn publish”. Nó phải trả lời bằng điều kiện có thể kiểm thử: **khi nào chạy, ai được gọi, kết quả/exception nào được thấy, side effect nào xảy ra, có thể retry hay bypass không, và chính sách còn đúng khi nhiều aspect cùng tham gia hay không**.

Khi aspect có thể đổi tham số, chặn thao tác, trả fallback, thay kết quả hoặc lỗi, đó là **một phần của hợp đồng API**, cần được review, version và kiểm thử tương tự mã nghiệp vụ. Một contract đúng đắn giúp consumer dùng hệ thống an toàn, vận hành dễ truy vết và nâng cấp AOP mà không gây breaking change ngoài dự kiến.
