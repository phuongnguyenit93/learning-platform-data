# Đánh đổi giữa biểu thức pointcut ngắn và độ chính xác của phạm vi

## 1. Vấn đề: viết ít ký tự có thật sự đơn giản hơn?

Trong **Aspect-Oriented Programming (AOP)**, một **pointcut** mô tả tập **join point** được chọn để áp dụng **advice**. Một join point là điểm trong mô hình thực thi mà công cụ AOP có thể can thiệp, chẳng hạn một lần thực thi phương thức hoặc một vị trí gọi phương thức, tùy cơ chế hỗ trợ.

Khi mới học pointcut, biểu thức thật ngắn thường có vẻ hấp dẫn:

```text
Chọn tất cả phương thức thuộc nhóm Service.
```

Chỉ một quy tắc có thể bao phủ hàng chục phương thức. Nhưng “tất cả Service” có thể gồm cả phương thức chẩn đoán, thao tác quản trị, getter, helper và những đường gọi không nằm trong chính sách. Khi thêm một phương thức mới, nó có thể bị aspect tác động mà không ai chủ động lựa chọn.

Ngược lại, một danh sách dài gồm các phương thức cụ thể có vẻ chính xác hơn, nhưng dễ **bỏ sót** phương thức mới, khó bảo trì và đòi hỏi cập nhật mỗi lần đổi tên hoặc chuyển kiểu.

Vì vậy, đánh đổi cần xem xét là:

- **Độ ngắn và khả năng diễn đạt:** biểu thức có dễ đọc, dễ giải thích ý định không?
- **Độ chính xác:** những điểm được chọn có đúng phạm vi cần thiết không?
- **Độ bao phủ:** điểm nào thuộc chính sách nhưng bị bỏ qua?
- **Tính ổn định:** thêm/chuyển/đổi tên phương thức có làm phạm vi thay đổi bất ngờ không?
- **Chi phí thực thi và kiểm thử:** bao nhiêu lần advice được chạy, phải xác minh những gì?
- **Tác động khi sai:** advice chỉ đo thời gian, hay có thể từ chối/đổi luồng nghiệp vụ?

**Biểu thức ngắn không đồng nghĩa phạm vi chính xác; biểu thức dài cũng không tự động đúng.** Mục tiêu là một pointcut có ý nghĩa rõ, đủ bao phủ và có thể chứng minh tập khớp phù hợp với chính sách.

Bài này bàn về **AOP nói chung**. Những biểu thức kiểu AspectJ được dùng làm ví dụ cho **cú pháp một công cụ cụ thể**; chúng không phải cú pháp mặc định của mọi ngôn ngữ hay cơ chế AOP.

## 2. Ba tập hợp phải phân biệt

Giả sử hệ thống có tập `U` gồm các join point **thực sự thuộc phạm vi mà công cụ có thể nhận diện/can thiệp**.

Ta xác định:

- **`D` (desired):** tập điểm **phải** có advice theo yêu cầu.
- **`S` (selected):** tập điểm mà pointcut **thực sự chọn**.
- **`U` (universe):** các điểm có thể xem xét trong mô hình và phạm vi weaving đang dùng.

Khi so sánh `S` với `D`:

| Kết quả | Ký hiệu | Ý nghĩa |
| --- | --- | --- |
| Đúng và được chọn | `TP = S ∩ D` | Điểm cần áp dụng và đã được chọn |
| Chọn thừa | `FP = S \ D` | Điểm không thuộc chính sách nhưng lại được chọn |
| Bỏ sót | `FN = D \ S` | Điểm phải được chọn nhưng pointcut không chọn |
| Đúng và không được chọn | `TN = U \ (S ∪ D)` | Điểm ngoài chính sách và không bị áp dụng |

Đây là **mô hình đánh giá phạm vi**, không phải thuật ngữ bắt buộc của một engine AOP.

Hình dung:

```text
                   TẬP PHẢI CAN THIỆP (D)
                 +--------------------------+
                 |  TP: chọn đúng           |
                 |                          |
     +-----------+--------------------------+------+
     |           | TẬP ĐƯỢC CHỌN (S)        |      |
     | FP:       |                          |      |
     | chọn thừa |       TP                 | FN:  |
     |           |                          | bỏ   |
     +-----------+--------------------------+ sót  |
                 |                          |      |
                 +--------------------------+------+
```

Sơ đồ chỉ là minh họa bằng nhãn, không biểu diễn chính xác hình học các tập. Hãy dùng công thức tập hợp ở bảng để suy luận.

Nếu `S = D`, phạm vi đúng theo yêu cầu đã mô hình hóa. Nếu `S` là tập con thực sự của `D`, có điểm bị bỏ sót. Nếu `S` chứa thêm điểm ngoài `D`, có chọn thừa. Một pointcut còn có thể mắc **cả hai lỗi cùng lúc**.

### 2.1. Precision và recall cho phạm vi pointcut

Có thể mượn hai thước đo để nói về chất lượng chọn điểm:

\[
\mathrm{precision} = \frac{TP}{TP + FP}
\]

\[
\mathrm{recall} = \frac{TP}{TP + FN}
\]

- **Precision cao:** phần lớn điểm được chọn đều thật sự cần advice.
- **Recall cao:** phần lớn điểm thật sự cần advice đã được chọn.

Nếu mẫu chọn **mọi điểm trong vũ trụ** thì recall có thể rất cao, nhưng precision thấp do quá nhiều điểm thừa. Nếu mẫu chỉ chọn **một phương thức thật chắc chắn**, precision có thể cao nhưng recall thấp vì còn các phương thức khác phải được xử lý.

Trong tập rỗng khiến mẫu số bằng 0, không nên báo bừa một tỷ lệ: cần xác định quy ước báo cáo “không áp dụng/không đo được” và kiểm tra trực tiếp số lượng điểm.

**Lưu ý về mô hình:** `D` phải được xác định từ chính sách độc lập với pointcut đang kiểm tra. Nếu dùng chính pointcut làm “đáp án đúng”, số liệu trở nên vòng tròn và không phát hiện lỗi.

## 3. Một ví dụ nhỏ: một chính sách kiểm toán có ba điểm hợp lệ

Giả sử hệ thống có tám phương thức cần xem xét trong một phạm vi weaving đã xác minh:

| STT | Kiểu và phương thức | Phải audit? | Lý do |
| ---: | --- | --- | --- |
| 1 | `CheckoutService.checkout()` | Có | Thao tác quan trọng |
| 2 | `CheckoutService.cancel()` | Có | Thao tác quan trọng |
| 3 | `CheckoutService.calculatePreview()` | Không | Chỉ tính xem trước |
| 4 | `CheckoutService.cleanup()` | Không | Công việc dọn dẹp nội bộ |
| 5 | `InventoryService.commit()` | Có | Thay đổi dữ liệu thực |
| 6 | `InventoryService.count()` | Không | Thao tác truy vấn |
| 7 | `InventoryService.cancel()` | Không | Không phải ranh giới kiểm toán theo chính sách giả định |
| 8 | `HealthProbe.check()` | Không | Chẩn đoán hệ thống |

Tập mong muốn `D` gồm ba phương thức ở dòng 1, 2 và 5. Yêu cầu này là **giả định của bài**, không phải quy tắc chung rằng mọi phương thức mang các tên đó đều phải kiểm toán.

### 3.1. Mẫu rộng và ngắn

Một mẫu “mọi phương thức trong kiểu kết thúc bằng Service” chọn bảy phương thức đầu.

```text
S_broad = tất cả phương thức của các kiểu *Service
TP = 3, FP = 4, FN = 0
precision = 3/7 ≈ 0,43
recall    = 3/3 = 1,00
```

Mẫu này **bao phủ đủ** nhưng **chọn thừa nhiều**. Nếu advice chỉ ghi một metric nhẹ, có thể chấp nhận mức độ rộng này trong một số trường hợp. Nếu advice kiểm tra quyền, từ chối thao tác hoặc thử lại, bốn điểm thừa có thể làm thay đổi hành vi ngoài mong muốn.

### 3.2. Mẫu hẹp theo danh sách rõ ràng

Một pointcut chỉ chọn `CheckoutService.checkout()` và `CheckoutService.cancel()`:

```text
S_narrow = { CheckoutService.checkout, CheckoutService.cancel }
TP = 2, FP = 0, FN = 1
precision = 2/2 = 1,00
recall    = 2/3 ≈ 0,67
```

Tập đã chọn **rất chính xác** nhưng bỏ sót `InventoryService.commit()`. Với audit bắt buộc, thiếu sót này có thể nghiêm trọng hơn việc ghi vài dòng log thừa.

### 3.3. Mẫu biểu đạt đúng ranh giới chính sách

Giả sử các phương thức phải audit được đánh dấu bằng metadata do chính sách quản lý, và công cụ AOP hỗ trợ chọn điểm bằng metadata ấy. Khi đó:

```text
S_policy = các method execution có dấu @Audited
TP = 3, FP = 0, FN = 0
precision = 1,00
recall    = 1,00
```

Mẫu thứ ba ngắn ở phía biểu thức chọn điểm, nhưng công sức đã được chuyển sang **quản trị metadata**: ai gắn dấu, ai xem xét thay đổi và có bảo đảm dấu xuất hiện trên mọi thao tác cần audit không? Một dấu gắn nhầm hoặc quên gắn vẫn tạo ra FP/FN. Không có cách chọn nào tự miễn phí về vận hành.

## 4. Sự đánh đổi thật sự: độ ngắn, độ bao phủ và tính ổn định

Có thể nhìn các chiến lược phổ biến:

| Chiến lược | Điểm mạnh | Rủi ro | Khi nào cân nhắc |
| --- | --- | --- | --- |
| Mẫu rộng theo package/tên kiểu | Gọn, bao phủ tự động khi có thành phần mới | Chọn thừa, bị ảnh hưởng bởi thay đổi tên/package | Telemetry chung ít tác động |
| Danh sách chữ ký tường minh | Dễ thấy ngay từng điểm, phạm vi hẹp | Bỏ sót điểm mới, dài và tốn bảo trì | Chính sách nhạy cảm, số điểm ít và ổn định |
| Mẫu theo quy ước đặt tên | Biểu thức ngắn, dễ áp dụng theo convention | Convention không chứng minh ngữ nghĩa | Quy ước được kiểm tra tự động |
| Mẫu kết hợp điều kiện và loại trừ | Cân bằng độ phủ và phạm vi | Biểu thức logic phức tạp, ưu tiên toán tử khó đọc | Có biên giới rõ, trường hợp loại trừ cụ thể |
| Metadata/annotation có ý nghĩa | Mục đích chính sách rõ, ít phụ thuộc tên | Phải quản lý độ chính xác của metadata | Hệ thống có quy trình quản trị |
| Named pointcut kết hợp | Tái sử dụng, dễ đặt tên ý nghĩa | Vẫn có thể che giấu độ rộng thực tế | Chính sách lớn hoặc nhiều advice |

Một biểu thức hai dòng có tên rõ và phạm vi kiểm thử được có thể **dễ bảo trì hơn** một biểu thức một dòng quá tổng quát. Ngược lại, liệt kê hàng trăm chữ ký không phải lúc nào cũng tốt hơn một quy tắc ngắn nhưng ổn định theo miền nghiệp vụ.

### 4.1. Số ký tự không phải thước đo độ phức tạp

Hai biểu thức cùng ngắn có thể khác rất nhiều:

```text
Chọn mọi phương thức.
Chọn mọi điểm thao tác có dấu audit đã được quản trị.
```

Câu đầu tiên ngắn vì **bỏ qua điều kiện biên**, câu thứ hai ngắn vì **ủy quyền tiêu chí rõ ràng** cho metadata và quy trình duy trì nó.

Do đó khi đánh giá phải tính cả chi phí để hiểu những điều kiện nằm **ngoài** chuỗi pointcut: metadata, quy ước tên, sơ đồ package, cấu hình weaving, thứ tự advice và thỏa thuận nhóm phát triển.

## 5. Phân biệt “pointcut đúng” với “advice thật sự chạy”

Tập `S` không chỉ là các tên khớp một biểu thức trên giấy. Một chương trình AOP thực sự chịu giới hạn bởi:

1. **Mô hình join point:** công cụ hỗ trợ method execution, method call, field access hay loại nào?
2. **Phạm vi weaving/interception:** những lớp và đường gọi nào được biến đổi hoặc đi qua đối tượng trung gian?
3. **Ngữ nghĩa pointcut:** mẫu tĩnh, điều kiện động và thứ tự đánh giá.
4. **Luồng advice:** lớp advice bao ngoài có thể không tiếp tục đến thao tác gốc.
5. **Dữ liệu thực tế:** một điều kiện động có thể chỉ khớp một số invocation.

Một pointcut có thể mô tả đúng chữ ký nhưng không có advice khi chạy nếu đường gọi đi trực tiếp qua target bên ngoài proxy. Một công cụ weaving khác có thể can thiệp tại phần thân phương thức. Vì vậy **độ chính xác của phạm vi** phải được xem xét cả ở mức **tập join point lý thuyết** lẫn **lần xuất hiện động thực tế**.

### 5.1. Method call và method execution không thể hoán đổi tùy tiện

Một phương thức `pay()` có thể được gọi từ nhiều nơi:

```text
CheckoutService.checkout() ---+
                              +---> PaymentGateway.pay()
RetryService.retry() ---------+
```

Một mẫu **method execution** hướng tới phần thực thi `pay()`; một mẫu **method call** xét các vị trí gọi tương ứng. Nếu chính sách nhằm đo mọi lần chạy phần thân thì chọn nhầm call pointcut có thể tạo tập điểm khác mong muốn. Nếu chính sách cần kiểm soát **chỉ lời gọi từ CheckoutService**, execution pointcut đơn độc có thể quá rộng.

Điều này độc lập với độ dài biểu thức: chỉ đổi một loại join point có thể thay đổi ý nghĩa rất lớn.

## 6. Ví dụ cú pháp công cụ: độ rộng theo kiểu và phương thức

Phần dưới minh họa với **cú pháp AspectJ**. Đây là ngôn ngữ pointcut cụ thể cho Java, không phải cú pháp chung bắt buộc của AOP.

Một biểu thức ngắn:

```aspectj
execution(* com.example..*Service.*(..))
```

Có thể hiểu là chọn method execution theo mẫu kiểu `*Service`, phương thức bất kỳ, kiểu trả về bất kỳ và danh sách tham số bất kỳ trong phạm vi package phù hợp. Biểu thức ngắn vì có nhiều wildcard.

Một biểu thức cụ thể hơn:

```aspectj
execution(* com.example.checkout.CheckoutService.checkout(..))
|| execution(* com.example.checkout.CheckoutService.cancel(..))
|| execution(* com.example.inventory.InventoryService.commit(..))
```

Mẫu này biểu đạt ba nhóm thực thi theo tên và kiểu rõ ràng. Nhưng cần kiểm tra **chữ ký overload**: `(..)` vẫn cho phép mọi danh sách tham số, nên nếu có nhiều overload cùng tên thì phạm vi có thể lớn hơn ba **chữ ký chính xác** dự kiến.

Có thể thêm ràng buộc tham số khi cần:

```aspectj
execution(* com.example.checkout.CheckoutService.checkout(java.lang.String))
```

Một hướng khác dùng dấu đánh dấu nghiệp vụ được quản trị:

```aspectj
execution(* com.example..*.*(..))
&& @annotation(com.example.policy.Audited)
```

Đây là ví dụ cú pháp của một công cụ hỗ trợ lựa chọn dựa trên annotation của phương thức tương ứng. Tên `com.example.policy.Audited` chỉ là giả định, cần có annotation và weaving phù hợp khi triển khai thật.

**Không nên sao chép nguyên văn các biểu thức trên vào bất kỳ công cụ AOP nào khác** rồi cho rằng wildcard, annotation matching hoặc loại join point có cùng ngữ nghĩa.

### 6.1. Wildcard rút ngắn ở vị trí nào?

| Cấu phần trong mẫu AspectJ | Ý nghĩa phổ biến | Rủi ro |
| --- | --- | --- |
| `*` ở kiểu trả về | Không ràng buộc kiểu trả về | Chọn cả `void`/giá trị khi chỉ muốn một kiểu |
| `*Service` ở kiểu | Chọn theo hậu tố tên kiểu | Tên kiểu không luôn phản ánh chính sách |
| `*` ở tên phương thức | Chọn mọi tên phương thức | Bao gồm cả helper/admin/getter |
| `(..)` ở danh sách tham số | Không ràng buộc số và kiểu tham số | Chọn các overload không mong muốn |
| `..` trong mẫu package | Mở phạm vi qua các cấp package phù hợp | Bao phủ namespace ngoài ý định |
| `+` trong type pattern | Chọn kiểu và các subtype phù hợp | Phạm vi thay đổi khi thêm lớp con |

Những ký hiệu có ngữ nghĩa theo **vị trí trong ngữ pháp**, khác Java regex hay file glob. Ví dụ `(*)` theo mẫu chữ ký AspectJ yêu cầu một tham số kiểu bất kỳ; `(..)` chấp nhận số tham số bất kỳ, bao gồm 0. Nếu nhầm hai ký hiệu này, pointcut có thể bỏ sót ngay cả khi tên lớp và tên phương thức đúng.

### 6.2. Biểu thức ngắn nhưng dễ gây lỗi khi refactor

Các quy ước `*Service` và `com.example..` liên kết pointcut với **tên và cấu trúc package**. Khi đổi tên lớp, di chuyển thành phần hoặc sinh thêm lớp helper trong package, tập điểm có thể thay đổi mà không xuất hiện lỗi biên dịch.

Đặc biệt nguy hiểm là sự thay đổi **vẫn hợp cú pháp**. Công cụ không thể tự biết rằng `CleanupService` mới **không thuộc ranh giới audit** nếu biểu thức chỉ yêu cầu hậu tố `Service`.

## 7. Logic AND/OR/NOT: tăng độ chính xác nhưng có chi phí đọc hiểu

Một cách hạn chế FP là kết hợp điều kiện:

```aspectj
execution(* com.example..*Service.*(..))
&& !within(com.example.internal..*)
```

Về ý tưởng, biểu thức vẫn chọn tập rộng theo `*Service` nhưng loại những join point được định nghĩa trong vùng `internal` được chỉ định. Điều này hữu ích khi **ranh giới loại trừ ổn định và có ý nghĩa**.

Nếu muốn ghép hai phạm vi rồi áp dụng cùng một điều kiện loại trừ:

```aspectj
(
    execution(* com.example.checkout..*Service.*(..))
    || execution(* com.example.inventory..*Service.*(..))
)
&& !within(com.example.internal..*)
```

Dấu ngoặc có tác dụng thực tế: nếu điều kiện loại trừ bị ghép vào **chỉ một nhánh OR** thì các điểm ngoài ý muốn ở nhánh còn lại vẫn có thể được chọn.

### 7.1. Khi nào nên tách named pointcut?

Khi một biểu thức đã có nhiều phần `&&`, `||`, `!` và lọc theo loại/kiểu, việc đặt tên các tập con giúp giảm tải đọc hiểu:

```text
businessOperations = các thao tác nghiệp vụ theo ranh giới đã quy định
excludedOperations = các điểm nội bộ/không thuộc chính sách
auditedOperations = businessOperations AND NOT excludedOperations
```

Đây là **mã giả ngôn ngữ trung lập**, không phải cú pháp khai báo pointcut thực tế. Mục tiêu là đặt tên theo **nghĩa chính sách**, sau đó triển khai bằng cú pháp tương ứng của công cụ.

Tách tên giúp biểu thức dễ đọc hơn, nhưng không làm một quy tắc sai trở nên đúng. Cần kiểm tra tập khớp sau khi ghép named pointcut.

### 7.2. Dấu NOT có thể che giấu thiếu sót trong chính sách

Giả sử loại mọi phương thức `get*` khỏi logging để giảm lưu lượng. Sau đó xuất hiện `getAndDelete()` thực hiện thay đổi dữ liệu. Nếu chỉ dựa vào tên, chính sách có thể **bỏ sót** thao tác nhạy cảm.

Do đó điều kiện loại trừ nên dựa vào ranh giới ngữ nghĩa đủ chắc, không chỉ dựa trên phỏng đoán rằng một tiền tố tên luôn mang nghĩa “đọc”.

## 8. Annotation và metadata: biểu thức ngắn nhưng chuyển gánh nặng sang thiết kế

Một cách làm cho pointcut vừa ngắn vừa chính xác là gắn **dấu có ý nghĩa chính sách** lên các điểm cần can thiệp:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audited {}
```

Đây là **đoạn Java minh họa**, phải thêm các import của `java.lang.annotation` để dùng như mã độc lập. Công cụ AOP cũng phải hỗ trợ điều kiện chọn điểm tương ứng.

Về thiết kế:

- **Ưu điểm:** ranh giới được thể hiện gần nơi khai báo thao tác; đổi tên phương thức không nhất thiết làm mất dấu.
- **Nhược điểm:** người viết phương thức có thể quên gắn dấu; chính sách dùng metadata phải có quy trình review.
- **Thách thức inheritance/interface:** dấu trên interface, lớp cha hay phương thức override có thể được xử lý khác nhau theo cách công cụ đọc metadata. Không nên đoán rằng dấu luôn được kế thừa tới mọi method execution.
- **Thách thức thêm mới:** nếu một thao tác mới cần audit mà chưa được đánh dấu, pointcut có thể không phát hiện và tạo **false negative**.

Có thể coi việc dùng metadata là chuyển từ **quy tắc nhận diện suy đoán theo tên** sang **khai báo chủ đích**, nhưng vẫn phải kiểm soát tính đầy đủ và độ tin cậy của khai báo.

### 8.1. Đặt metadata ở ranh giới nào?

Nếu chính sách liên quan đến một **thao tác nghiệp vụ được công khai**, dấu nên phản ánh ranh giới thực mà người gọi sử dụng. Nếu đặt dấu trên helper nội bộ, aspect có thể chạy nhiều lần cho một thao tác, tạo audit dư thừa.

Mức độ đúng của metadata phải được xem xét cùng với mô hình join point: chọn **method execution** trên implementation có thể khác việc chọn **method call** ở các vị trí bên gọi.

## 9. Cân nhắc hậu quả theo loại advice

Cùng một sai lệch FP/FN có thể ít hoặc rất nghiêm trọng tùy advice.

| Loại chính sách | Khi chọn thừa (FP) | Khi bỏ sót (FN) |
| --- | --- | --- |
| Ghi metric hiệu năng | Overhead, tăng cardinality/noise | Thiếu số liệu cho thao tác cần đo |
| Logging kỹ thuật | Log rác, có nguy cơ lộ dữ liệu | Không đủ dấu vết khi debug |
| Kiểm toán bắt buộc | Audit sự kiện không thuộc chính sách, tăng chi phí | Thiếu bản ghi bắt buộc |
| Kiểm tra quyền | Chặn nhầm chức năng hoặc tăng độ trễ | Đường truy cập cần bảo vệ có thể bị bỏ qua |
| Retry | Thực thi lại thao tác không an toàn, tác dụng phụ trùng | Bỏ qua thao tác cần chống lỗi tạm thời |
| Chuyển đổi ngoại lệ | Caller nhận lỗi bị đổi ngoài mong muốn | Mã lỗi không được chuẩn hóa như yêu cầu |

**Không có một “mức precision/recall tốt nhất” chung cho mọi aspect.** Một chính sách kiểm soát quyền có thể không chấp nhận bất kỳ FN nào ở các đường vào cần bảo vệ; một chính sách đo thời gian có thể chấp nhận vài FP nếu đủ nhẹ và có ngân sách tài nguyên.

Với những thao tác quan trọng, đừng giải quyết rủi ro bằng một wildcard rộng một cách máy móc. Cần bảo đảm **mọi đường thực thi bắt buộc** đều đi qua cơ chế can thiệp và không còn đường gọi ngoài phạm vi.

## 10. Tập điểm tĩnh và số lần xuất hiện động không giống nhau

Một mẫu khớp mười phương thức chưa chắc tốn chi phí hơn mẫu khớp hai phương thức.

Giả sử:

- Pointcut A chọn mười phương thức hiếm khi chạy.
- Pointcut B chọn đúng hai phương thức được gọi hàng triệu lần mỗi phút.

Nếu cùng một advice tốn chi phí (c) trên mỗi lần chạy, chi phí gần đúng phụ thuộc vào **tần suất các invocation được advice thực sự xử lý**, không chỉ số lượng tên phương thức:

\[
\mathrm{overhead} \approx \sum_{j \in S} \mathrm{invocations}(j) \times \mathrm{costOfAdvice}(j)
\]

Công thức là mô hình đơn giản: chưa bao gồm chi phí đánh giá điều kiện động, khởi tạo/cấu hình, contention, ảnh hưởng cache, JIT hoặc I/O bất đồng bộ.

Vì vậy nên đo hai khía cạnh:

1. **Coverage theo join-point shadow:** bao nhiêu vị trí/chữ ký cần được chọn; có FP/FN ở cấu trúc tĩnh không?
2. **Coverage theo invocation thực tế:** những đường chạy được quan sát có qua advice đúng số lần, đúng ngữ cảnh hay không?

Một pointcut có vẻ chính xác ở mức tên vẫn có thể tạo overhead lớn nếu đi qua thao tác rất nóng, hoặc tạo thiếu sót nếu invocation đi theo đường mà proxy không can thiệp được.

### 10.1. Điều kiện động làm tăng độ chính xác có thể tốn chi phí

Một pointcut có thể kết hợp điều kiện cấu trúc và điều kiện theo kiểu đối tượng hay giá trị tham số ở runtime. Điều này có thể giảm FP theo **từng invocation** nhưng đòi hỏi đánh giá điều kiện khi chạy.

Không nên đặt một phép gọi mạng hoặc truy vấn dữ liệu nặng vào logic chọn điểm chỉ để thu được một biểu thức nhìn “thật ngắn”. Độ chính xác phải được cân nhắc với khả năng đo lường và chi phí thực thi.

## 11. Ví dụ Java 17 chạy được: tính TP, FP, FN cho ba quy tắc chọn

Để thấy rõ đánh đổi, ta sẽ dùng **reflection của JDK** để mô phỏng quá trình phân loại các phương thức. Ví dụ này **không phải engine AOP** và không thực hiện weaving: nó chỉ tính xem ba quy tắc chọn theo metadata có khớp tập mong muốn hay không.

Tạo tệp `PointcutScopeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Stream;

public class PointcutScopeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Audited {}

    static class CheckoutService {
        @Audited public void checkout() {}
        @Audited public void cancel() {}
        public void calculatePreview() {}
        public void cleanup() {}
    }

    static class InventoryService {
        @Audited public void commit() {}
        public void count() {}
        public void cancel() {}
    }

    static class HealthProbe {
        public void check() {}
    }

    record Rule(String name, Predicate<Method> match) {}

    static void report(Rule rule, List<Method> methods) {
        int truePositive = 0;
        int falsePositive = 0;
        int falseNegative = 0;

        for (Method method : methods) {
            boolean desired = method.isAnnotationPresent(Audited.class);
            boolean selected = rule.match().test(method);

            if (desired && selected) truePositive++;
            if (!desired && selected) falsePositive++;
            if (desired && !selected) falseNegative++;
        }

        int selected = truePositive + falsePositive;
        int required = truePositive + falseNegative;
        double precision = selected == 0 ? 0 : (double) truePositive / selected;
        double recall = required == 0 ? 0 : (double) truePositive / required;

        System.out.printf(
                Locale.ROOT,
                "%s: selected=%d, TP=%d, FP=%d, FN=%d, precision=%.2f, recall=%.2f%n",
                rule.name(), selected, truePositive, falsePositive,
                falseNegative, precision, recall
        );
    }

    public static void main(String[] args) {
        List<Method> methods = Stream.of(
                CheckoutService.class,
                InventoryService.class,
                HealthProbe.class
        ).flatMap(type -> Arrays.stream(type.getDeclaredMethods()))
         .sorted(Comparator.comparing(
                 m -> m.getDeclaringClass().getSimpleName() + "." + m.getName()
         ))
         .toList();

        Rule broad = new Rule(
                "broad",
                m -> m.getDeclaringClass().getSimpleName().endsWith("Service")
        );

        Rule narrow = new Rule(
                "narrow",
                m -> m.getDeclaringClass() == CheckoutService.class
                        && Set.of("checkout", "cancel").contains(m.getName())
        );

        Rule explicit = new Rule(
                "explicit",
                m -> m.isAnnotationPresent(Audited.class)
        );

        report(broad, methods);
        report(narrow, methods);
        report(explicit, methods);
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac PointcutScopeDemo.java
java PointcutScopeDemo
```

Đầu ra:

```text
broad: selected=7, TP=3, FP=4, FN=0, precision=0.43, recall=1.00
narrow: selected=2, TP=2, FP=0, FN=1, precision=1.00, recall=0.67
explicit: selected=3, TP=3, FP=0, FN=0, precision=1.00, recall=1.00
```

### 11.1. Vì sao có kết quả đó?

- Danh sách phương thức gồm bốn phương thức của `CheckoutService`, ba của `InventoryService` và một của `HealthProbe`.
- Chính sách minh họa coi ba phương thức có `@Audited` là tập mong muốn.
- `broad` chọn toàn bộ bảy phương thức trong hai lớp có hậu tố `Service`, nên chọn đúng ba và thừa bốn.
- `narrow` chỉ chọn `checkout` và `cancel` của `CheckoutService`; bỏ sót `InventoryService.commit`.
- `explicit` đọc dấu `@Audited` đã gắn trên ba phương thức, nên khớp đúng theo tiêu chuẩn của ví dụ.

**Giới hạn đặc biệt của ví dụ:** `explicit` đạt kết quả hoàn hảo vì định nghĩa desired cũng lấy từ cùng một annotation. Trong hệ thống thật, **không được dùng cách này để chứng minh annotation đã được gắn đủ**. Đáp án đúng cần đến từ yêu cầu nghiệp vụ hoặc bản kiểm kê được kiểm chứng độc lập. Ví dụ chỉ chứng minh quan hệ giữa các tập lựa chọn đã định nghĩa, không chứng minh chính sách audit trên hệ thống thực đã được đáp ứng.

### 11.2. Chương trình Java thuần có gì khác pointcut AOP?

- `Predicate<Method>` ở đây chỉ là một hàm kiểm tra `Method`, không định nghĩa advice hay weave join point.
- `getDeclaredMethods()` chỉ trả những phương thức được khai báo trong các lớp được duyệt; không phải toàn bộ call sites hay mọi điểm runtime có thể can thiệp.
- Mẫu hậu tố `Service` được thực hiện bằng `endsWith` của Java, **không phải parser wildcard của AspectJ**.
- `@Audited` là metadata được đọc bằng reflection; việc một công cụ AOP thật nhận diện dấu trên các loại join point ra sao cần xác minh theo công cụ đó.

Điều nên mang sang AOP thực tế là **cách lập bảng yêu cầu và đo chọn thừa/bỏ sót**, chứ không sao chép bộ mô phỏng này thành một cơ chế weaving.

## 12. Độ chính xác còn thay đổi khi mã tiến hóa

Một pointcut có thể đúng hoàn toàn hôm nay nhưng lệch sau một lần refactor.

### 12.1. Thêm phương thức mới

Ban đầu `*Service.*(..)` bao phủ đúng các thao tác cần đo. Sau đó một kỹ sư thêm `DebugService.dumpRawState()`. Mẫu có thể tự chọn luôn phương thức mới, dù người viết chính sách chưa xem xét. Đây là **FP do mở rộng phạm vi tự động**.

Với danh sách tường minh, phương thức mới `InventoryService.adjustStock()` cần audit có thể bị bỏ qua. Đây là **FN do thiếu cập nhật**.

### 12.2. Đổi tên hoặc di chuyển package

Một phương thức chuyển từ `com.example.business` sang `com.example.internal` có thể không còn khớp mẫu cũ, dù chức năng nghiệp vụ không đổi. Ngược lại, đổi tên một helper thành `*Service` có thể khiến nó bị áp dụng advice. Vì vậy việc refactor nên được xem như một thay đổi **có thể ảnh hưởng tới tập chọn**.

### 12.3. Overload, override và phân cấp kiểu

Một mẫu cho `save(..)` có thể tự chọn overload mới `save(List<Item>)` dù chỉ overload `save(Item)` thuộc chính sách. Mẫu theo kiểu `BaseService+` có thể bao phủ subtype được thêm mới.

Với override, interface và phương thức sinh từ compiler, cách nhận diện declaring type và annotation có thể khác nhau theo mô hình AOP. Không nên suy từ chữ ký nhìn trong source rằng mọi cơ chế interception đều chọn cùng một điểm.

### 12.4. Từ truy vết tĩnh tới kiểm thử hồi quy

Muốn giảm rủi ro, nên có một báo cáo hoặc phép kiểm tra tái tạo được danh sách các join point khớp với pointcut quan trọng sau mỗi thay đổi. Khi số điểm thay đổi, nhóm phát triển phải thấy được điểm nào được thêm/bỏ và vì sao.

Cần phân biệt việc so sánh **danh sách tĩnh** với việc xác minh **đường chạy thực tế**. Cả hai hữu ích vì một công cụ chỉ chặn lời gọi qua proxy có thể bỏ qua những đường gọi dù mẫu chữ ký khớp.

## 13. Khi nào chọn ngắn, khi nào chọn rõ từng điểm?

Không có công thức áp dụng chung. Có thể dựa vào **mức độ tác động** của advice:

### 13.1. Chính sách quan sát kỹ thuật, chi phí thấp

Ví dụ đo thời gian hoặc đếm số lần gọi. Một mẫu tương đối rộng có thể hữu ích nếu:

- Những điểm bổ sung không làm đổi kết quả hoặc ngoại lệ.
- Overhead đã được đo và chấp nhận.
- Dữ liệu nhạy cảm không bị log tự động.
- Có khả năng loại trừ những hot path hoặc vùng mã đặc biệt.
- Thêm phương thức mới được theo dõi trong báo cáo coverage.

Điều này **không có nghĩa** logging luôn an toàn: ghi tham số nhạy cảm, gọi `toString()` trên đối tượng lớn hoặc ghi log I/O nặng vẫn có thể tạo rủi ro.

### 13.2. Chính sách có tác động hành vi hoặc kiểm soát

Với advice có thể từ chối thao tác, đổi kết quả/ngoại lệ, khởi tạo giao dịch hoặc thử lại, cần ưu tiên ranh giới có chủ đích và khả năng kiểm chứng:

- Tập các thao tác được phê duyệt rõ ràng.
- Định nghĩa những đường vào bắt buộc.
- Kiểm thử FP và FN nghiêm ngặt.
- Xác minh thứ tự khi nhiều aspect cùng khớp.
- Đánh giá side effect nếu advice gọi lại phần nghiệp vụ.
- Kiểm chứng hoạt động đúng trên cơ chế weaving thực tế, nhất là lời gọi nội bộ và các đường vào khác.

Một pointcut “đủ ngắn để nhớ” nhưng không thể giải thích bằng chính sách là điểm bắt đầu của rủi ro.

## 14. Tách độ phức tạp biểu thức khỏi độ phức tạp vận hành

Giả sử hai thiết kế:

**Thiết kế A:** một biểu thức wildcard duy nhất, không có quy trình xác minh tự động. Người mới đọc chỉ biết nó chọn các lớp có hậu tố `Service`.

**Thiết kế B:** named pointcut `auditedOperations`, tập được chọn xác định bằng dấu đánh dấu có tài liệu, có kiểm thử bảo đảm các thao tác thuộc danh sách yêu cầu được gắn dấu và được weaving.

B có thể viết dài hơn về tổng hệ thống, nhưng **dễ kiểm chứng**. Ngược lại, với một chương trình chỉ có hai phương thức cố định, danh sách tường minh có thể thực tế hơn cả metadata và kiểm thử phức tạp.

Một “biểu thức tối ưu” là biểu thức giảm **chi phí hiểu và duy trì toàn bộ chính sách**, không đơn thuần giảm độ dài chuỗi pointcut.

### 14.1. Bốn câu hỏi khi review

1. **Ý định:** ta muốn chọn nhóm thao tác nào, theo quy tắc nghiệp vụ hay kỹ thuật nào?
2. **Phạm vi:** biểu thức chọn những điểm nào hôm nay, và sẽ tự chọn những điểm nào khi thêm mã?
3. **Bỏ sót:** điểm nào phải chạy advice nhưng không nằm trong tập chọn?
4. **Chứng cứ:** bảng ca kiểm thử và kết quả weaving/runtime nào chứng minh hai câu trả lời trên?

Nếu không trả lời được, nên thay đổi ranh giới hoặc bổ sung chứng cứ trước khi rút ngắn biểu thức.

## 15. Quy trình thiết kế một pointcut có phạm vi chính xác

### Bước 1 — Viết chính sách bằng ngôn ngữ nghiệp vụ

Ví dụ: “Ghi audit một lần cho mỗi thao tác xác nhận thay đổi đơn hàng; không ghi audit cho các phép tính xem trước.”

Cách viết này rõ hơn “chọn `*Service` và loại `get*`”, vì nó chỉ ra **lý do** lựa chọn, không chỉ dấu hiệu tên.

### Bước 2 — Xác định loại join point

Chọn điểm method call hay method execution? Với một thao tác lồng nhau, advice cần chạy ở boundary ngoài cùng hay trên mọi lời gọi nội bộ? Loại điểm là một phần của yêu cầu.

### Bước 3 — Liệt kê tập dương tính và âm tính

Ghi một danh sách độc lập:

- Những phương thức, đường gọi hoặc thao tác **bắt buộc** có advice.
- Những thao tác **không được** có advice.
- Trường hợp biên: overload, subclass, helper, self-invocation, public/private, async và lỗi.

Không nhất thiết phải kiểm kê mọi method trong hệ thống, nhưng điểm quan trọng phải có chứng cứ rõ.

### Bước 4 — Chọn tiêu chí tương đối ổn định

Ưu tiên tiêu chí gắn với hợp đồng được quản trị: nhóm chức năng, annotation, tên kiểu/package theo convention có kiểm thử, hoặc chữ ký tường minh khi cần.

### Bước 5 — Viết pointcut dễ đọc

Kết hợp điều kiện bằng named pointcut, ghi ngoặc `AND/OR/NOT` rõ và chú thích lý do loại trừ. Tránh kéo dài vô hạn các ngoại lệ để cứu một wildcard quá rộng; khi đó có thể cần thay đổi cách xác định ranh giới.

### Bước 6 — Kiểm tra kết quả khớp tĩnh

Nếu công cụ hỗ trợ thống kê/danh sách điểm weaving, so sánh với tập dương và âm. Một biểu thức hợp cú pháp nhưng **không khớp điểm nào** không phải thành công.

### Bước 7 — Kiểm tra đường chạy động

Thực thi các thao tác thật và kiểm tra advice chạy đúng lúc. Đặc biệt quan tâm lời gọi qua proxy, tự gọi phương thức, lớp nạp động, ngữ cảnh đa luồng và điều kiện phụ thuộc tham số.

### Bước 8 — Đo overhead và kiểm soát thay đổi

Với hot path, đo tần suất và chi phí advice; với chính sách quan trọng, bảo đảm các lần thay đổi source và weaving làm chạy lại kiểm thử coverage. Đừng cố loại hết FP bằng điều kiện runtime rất tốn kém mà không đo tác động.

## 16. Những ca kiểm thử nên có

| Ca | Mục tiêu | Lỗi phát hiện |
| --- | --- | --- |
| Phương thức thuộc tập bắt buộc | Advice chạy đúng một lần tại boundary quy định | FN |
| Phương thức ngoài chính sách | Advice không chạy | FP |
| Overload mới | Chọn đúng chữ ký/kiểu tham số | FN hoặc FP do `(..)` |
| Thêm lớp cùng hậu tố tên | Không mở phạm vi trái ý | FP do wildcard |
| Đổi package/rename | Phạm vi vẫn phản ánh hợp đồng | FN/FP khi refactor |
| Lời gọi nội bộ | Chạy đúng theo cơ chế weaving đã chọn | FN ở proxy boundary |
| Hai aspect cùng chọn | Thứ tự và tác động đúng | Sai ngữ nghĩa dù điểm khớp |
| Ngoại lệ từ nghiệp vụ | Advice giữ/đổi lỗi theo hợp đồng | Nuốt hoặc che lỗi |
| Nhiều invocation đồng thời | Trạng thái theo lần gọi độc lập | Nhiễu context |
| Phương thức trả future | Đo đúng ranh giới kết thúc | Nhầm method return với task completion |

**Một bài kiểm thử chỉ xác nhận advice đã chạy ở ít nhất một nơi là chưa đủ.** Cần chứng minh những nơi không mong muốn không bị ảnh hưởng và những đường bắt buộc không bỏ sót.

## 17. Các sai lầm thường gặp

**“Biểu thức ngắn hơn tức là pointcut tốt hơn.”** Sai. Độ ngắn không đo được FP/FN, khả năng bảo trì hoặc hậu quả khi aspect chạy sai.

**“Dùng wildcard thật rộng để chắc chắn không bỏ sót.”** Có thể tăng recall nhưng tạo FP lớn. Với advice có tác dụng phụ, lỗi chọn thừa nguy hiểm.

**“Liệt kê mọi tên phương thức sẽ không bao giờ sai.”** Danh sách vẫn có thể thiếu phương thức mới, khớp quá rộng do overload hoặc sai loại join point.

**“`*Service` bảo đảm toàn bộ phương thức là nghiệp vụ.”** Không. Tên kiểu chỉ là quy ước; các helper hoặc thao tác quản trị có thể nằm trong cùng lớp.

**“Annotation khiến phạm vi đúng tuyệt đối.”** Không. Dấu có thể thiếu, thừa, bị khai báo ở vị trí không được công cụ nhận diện hoặc không được weaving trên một đường chạy.

**“Chỉ cần kiểm thử kết quả trả về.”** Chưa đủ. Advice có thể chạy thừa mà không đổi giá trị nhưng gây log nhạy cảm, overhead hoặc thứ tự sai.

**“Pointcut khớp trên lý thuyết thì advice luôn chạy.”** Sai. Cần đúng mô hình join point, phạm vi weaving, đường gọi và điều kiện động.

**“Mọi điểm được chọn đều tốn chi phí ngang nhau.”** Sai. Tần suất invocation, mức độ nóng, loại advice và chi phí đánh giá điều kiện có thể khác nhau rất lớn.

**“Loại `get*` có nghĩa đã loại các thao tác chỉ đọc.”** Không thể suy luận ngữ nghĩa nghiệp vụ từ tiền tố; một phương thức có thể có side effect dù tên bắt đầu bằng `get`.

## 18. Bài tập tự đánh giá

**Bài 1.** Tập bắt buộc gồm bốn phương thức. Pointcut A chọn cả bốn cộng sáu phương thức khác. Hãy tính precision và recall.

Có `TP=4`, `FP=6`, `FN=0`; precision bằng `4/10 = 0,40`, recall bằng `4/4 = 1,00`. Mẫu bao phủ đủ nhưng chọn thừa.

**Bài 2.** Pointcut B chỉ chọn ba trong bốn phương thức bắt buộc và không chọn thừa. Nó tốt hơn pointcut A không?

Precision của B bằng `1,00`, recall bằng `3/4 = 0,75`. Không thể quyết định chỉ bằng một con số; phải xem **hậu quả bỏ sót** và **hậu quả chọn thừa** theo chính sách. Nếu bốn phương thức đều bắt buộc kiểm toán, FN có thể không chấp nhận được.

**Bài 3.** Một biểu thức `*Service.*(..)` bất ngờ áp dụng advice cho helper mới. Nên sửa thế nào?

Trước hết xác định helper có thuộc chính sách không, sau đó chọn ranh giới thích hợp: kiểu/package chính xác hơn, một dấu metadata được quản trị, named pointcut có điều kiện hợp lý hoặc danh sách điểm tường minh. Thêm ca âm tính để tránh tái phát.

**Bài 4.** Một mẫu hẹp chỉ chọn `save(String)`, nhưng chương trình thêm `save(List<Item>)` cũng cần kiểm toán. Vì sao có FN?

Mẫu ràng buộc chữ ký cũ; overload mới chưa thuộc tập khớp. Nếu muốn cả hai, sửa pointcut theo yêu cầu và kiểm thử, không mặc định mở thành `save(..)` nếu các overload khác có ý nghĩa khác.

**Bài 5.** Pointcut chọn đúng `checkout()` theo chữ ký nhưng một đường gọi không chạy advice. Cần kiểm tra gì?

Kiểm tra join point là call hay execution, phạm vi weaving, lời gọi có đi qua proxy không, điều kiện động có khớp không và advice bao ngoài có chặn chuyển tiếp không. Đó có thể là **lỗi coverage runtime** dù mẫu chữ ký đúng.

**Bài 6.** Một chính sách logging có precision cao nhưng khiến ứng dụng chậm. Có mâu thuẫn không?

Không. Precision đo tỷ lệ chọn đúng, không đo **tần suất** các join point hay chi phí của advice. Một điểm được chọn đúng nhưng cực kỳ nóng vẫn có thể chiếm nhiều tài nguyên.

## 19. Những nguyên tắc thực hành đáng giữ

1. **Bắt đầu từ chính sách, không bắt đầu từ wildcard.** Xác định tập cần can thiệp độc lập với biểu thức.
2. **Xác định loại join point và phạm vi weaving.** Một mẫu tĩnh đúng chưa bảo đảm mọi đường chạy được bao phủ.
3. **Tối ưu cả chọn đúng lẫn tránh chọn nhầm.** Luôn kiểm tra TP, FP, FN theo mức độ rủi ro.
4. **Ưu tiên ranh giới có ý nghĩa và được quản trị.** Annotation, package convention và danh sách tường minh đều cần kiểm chứng.
5. **Giữ biểu thức dễ giải thích.** Dùng điều kiện và named pointcut rõ ràng thay vì chỉ cố tiết kiệm ký tự.
6. **Xem refactor là thay đổi có thể ảnh hưởng chính sách.** So sánh tập điểm được chọn trước/sau khi thay đổi.
7. **Đo chi phí runtime.** Số join point tĩnh không phản ánh hoàn toàn overhead của advice.
8. **Bảo vệ hành vi nghiệp vụ.** Với advice có thể ngăn, thử lại hoặc đổi lỗi, phạm vi sai có thể tạo side effect nghiêm trọng.

Một pointcut tốt là pointcut có **ranh giới đúng, có thể giải thích, kiểm thử được và ổn định đủ lâu trước thay đổi mã**. Độ ngắn chỉ là một thuộc tính phụ trợ. Giá trị thật của biểu thức đến từ khả năng biểu đạt đúng chính sách và chứng minh được điều gì sẽ xảy ra tại các join point khi hệ thống vận hành.
