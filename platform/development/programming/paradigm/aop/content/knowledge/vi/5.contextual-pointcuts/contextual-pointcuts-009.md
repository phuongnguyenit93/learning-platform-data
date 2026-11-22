# Chi phí và khả năng kiểm thử của điều kiện động trong pointcut AOP

## 1. Điều kiện động là gì, và vì sao cần quan tâm đến chi phí?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **pointcut** xác định các **join point** mà advice có thể được áp dụng. Join point là điểm trong mô hình thực thi có thể can thiệp, ví dụ một lần thực thi phương thức hoặc vị trí gọi phương thức nếu cơ chế AOP hỗ trợ.

Có những điều kiện chọn điểm có thể suy ra từ **cấu trúc chương trình**: loại join point, chữ ký phương thức, kiểu khai báo, tên package, annotation tĩnh. Nhưng có những điều kiện chỉ xác định được khi một **lần thực thi cụ thể** xảy ra: đối tượng thực sự nhận lời gọi, đối số runtime, trạng thái ngữ cảnh, hoặc việc luồng điều khiển hiện đang nằm trong một vùng thực thi nhất định.

Nhóm thứ hai là **điều kiện động (dynamic conditions)**. Chúng hữu ích vì cho phép một aspect can thiệp chính xác hơn theo ngữ cảnh, nhưng việc kiểm tra thường phải diễn ra trong đường chạy thực tế.

Ví dụ yêu cầu:

> Chỉ ghi nhận kiểm toán chuyên sâu khi thao tác chuyển khoản có số tiền lớn và thuộc nhóm tài khoản cần theo dõi.

Có thể lọc tĩnh theo chữ ký thao tác `transfer`. Nhưng một chữ ký `transfer(String,long)` không cho biết lần gọi hiện tại mang số tiền 50 hay 5.000. Quy tắc theo giá trị phải được đánh giá ở thời điểm chạy tương ứng, nếu công cụ và thiết kế cho phép.

Hai câu hỏi chính của bài:

1. **Chi phí:** việc lựa chọn động tốn bao nhiêu tài nguyên ở mỗi lần xuất hiện join point, và khi nào tổng chi phí trở nên đáng kể?
2. **Khả năng kiểm thử:** làm thế nào chứng minh advice chạy đúng trên các ngữ cảnh cần thiết, không chạy ở ngữ cảnh bị loại, và giữ đúng hành vi khi gặp lỗi, đồng thời hoặc bất đồng bộ?

Bài học áp dụng cho **AOP tổng quát**. Khi nhắc đến cú pháp của một công cụ cụ thể, ví dụ đó chỉ minh họa ngữ nghĩa tương ứng; không có giả định rằng mọi công cụ hỗ trợ cùng một tập join point và cách biểu đạt pointcut.

## 2. Tách điều kiện tĩnh và động

Xem một thao tác nghiệp vụ:

```java
Receipt transfer(String accountId, long amount);
```

Đây là **chữ ký Java minh họa**, chưa phải chương trình độc lập vì `Receipt` cần có định nghĩa. Những thông tin có thể nhận diện từ cấu trúc gồm tên `transfer`, kiểu trả về `Receipt`, kiểu tham số `String,long` và kiểu khai báo của phương thức.

Các dữ liệu như `accountId="VIP-42"`, `amount=5000` hoặc đối tượng runtime thuộc lớp triển khai nào lại liên quan đến **một lần gọi cụ thể**.

| Tiêu chí | Điều kiện tĩnh | Điều kiện động |
| --- | --- | --- |
| Nguồn thông tin | Loại join point, khai báo phương thức, metadata cấu trúc | Đối tượng, đối số, trạng thái và ngữ cảnh khi chạy |
| Thời điểm thường có thể đánh giá | Biên dịch, nạp mã hoặc bước chuẩn bị chọn điểm | Khi join point xuất hiện hoặc khi ngữ cảnh được cập nhật |
| Ví dụ | Tên phương thức là `transfer` | `amount > 1000` |
| Tần suất đánh giá | Có thể xử lý hoặc tối ưu sớm tùy công cụ | Có thể phải kiểm tra trên từng invocation tiềm năng |
| Khả năng thay đổi giữa hai lần gọi | Thường ổn định với cùng vị trí/định nghĩa mã | Có thể khác hoàn toàn |
| Rủi ro chính | Chọn sai tập điểm cấu trúc | Chi phí runtime, thay đổi trạng thái và kiểm thử nhiều nhánh |

Một pointcut có thể chứa **cả hai phần**. Thường nên dùng điều kiện tĩnh để giảm tập điểm có khả năng bị can thiệp, rồi áp dụng điều kiện động ở nơi còn cần thiết.

**Điều kiện động không nhất thiết chậm.** Một phép kiểm tra `amount > 1000` đơn giản có thể rất rẻ. Điều quan trọng là **số lần kiểm tra**, dữ liệu được truy cập, tác động lên đường chạy nóng và cách thực hiện của công cụ.

### 2.1. Join-point shadow và lần xuất hiện thực tế

Một vị trí mã có thể phát sinh nhiều lần thực thi:

```java
for (int i = 0; i < 100; i++) {
    gateway.transfer("VIP-42", i * 100L);
}
```

Đoạn trên là **mã minh họa** với `gateway` được giả định đã khai báo.

Một vị trí lời gọi tĩnh có thể phát sinh **100 lần gọi**. Nếu cơ chế AOP chọn được loại join point tương ứng và có điều kiện theo số tiền, việc đánh giá điều kiện có thể diễn ra trên các lần gọi này, dù cuối cùng chỉ một phần được advice xử lý.

Đừng suy ra chi phí chỉ từ **số phương thức khớp mẫu**. Một phương thức chạy 10 triệu lần có thể tạo nhiều phép kiểm tra hơn hàng trăm phương thức hiếm khi chạy.

## 3. Luồng xử lý pointcut có điều kiện động

Một mô hình khái niệm:

```text
Mã được cấu hình / weaving
         |
         v
Bộ lọc cấu trúc tĩnh
         |
         +-- Không thuộc phạm vi ----------> Không cần kiểm tra động cho điểm này
         |
         v
Join point xuất hiện khi chạy
         |
         v
Lấy ngữ cảnh cần thiết (args / target / control flow ...)
         |
         v
Đánh giá điều kiện động
         |
         +-- Không khớp -------------------> Tiếp tục xử lý theo ngữ nghĩa công cụ
         |
         +-- Khớp -------------------------> Áp dụng advice tương ứng
                                                 |
                                                 v
                                        Thao tác gốc / chuỗi advice
```

Sơ đồ mô tả **mục đích tách hai giai đoạn**, không khẳng định mọi bộ máy AOP thực thi chính xác thành một chuỗi hàm như hình. Một số công cụ có thể tối ưu, kết hợp, hoán đổi các kiểm tra thuần túy hoặc biểu diễn chúng trong mã được weaving.

Các tình huống cần phân biệt:

- **Không thuộc loại join point được hỗ trợ:** không có can thiệp tương ứng, dù biểu thức mô tả trên giấy có vẻ đúng.
- **Khớp phần tĩnh nhưng trượt điều kiện động:** lần gọi không nhận advice được ràng buộc với điều kiện đó.
- **Khớp toàn bộ:** advice có thể chạy, nhưng một advice bao ngoài cũng có thể thay đổi việc chuyển tiếp tới các phần bên trong.
- **Bản thân điều kiện ném lỗi:** cần biết hợp đồng công cụ và chính sách ứng dụng; không mặc định lỗi được bỏ qua.
- **Ngữ cảnh bị thay đổi trong chuỗi advice:** giá trị được kiểm tra lúc nào có thể ảnh hưởng kết quả lựa chọn.

**Pointcut được chọn** và **phần nghiệp vụ thực sự chạy** là hai sự kiện khác nhau. Một around advice có thể từ chối hoặc không tiếp tục thao tác gốc nếu được thiết kế cho phép.

## 4. Những nguồn chi phí của điều kiện động

Không chỉ có thời gian của phép so sánh. Chi phí có thể xuất hiện ở nhiều lớp:

| Thành phần | Nguồn chi phí | Ví dụ |
| --- | --- | --- |
| Kiểm tra predicate | So sánh giá trị, kiểm tra kiểu, nhánh điều kiện | `amount > threshold` |
| Lấy ngữ cảnh | Truy cập args, target, metadata runtime | Trích xuất đối số |
| Phân bổ bộ nhớ | Tạo mảng/đối tượng bọc ngữ cảnh | Mỗi lần gọi tạo bản sao args |
| Truy cập trạng thái | Map, cấu hình, đồng bộ hoặc thread context | Tra chính sách theo tenant |
| Điều kiện theo luồng điều khiển | Theo dõi phạm vi gọi lồng nhau | Kiểm tra đang ở trong một flow |
| Cơ chế interception | Chuyển qua proxy/handler hoặc mã đã weaving | Một tầng gọi gián tiếp |
| Advice sau khi khớp | Logging, audit, metrics, retry | Ghi log hoặc phát sự kiện |
| Ảnh hưởng gián tiếp | Cache miss, branch misprediction, GC, contention | Tăng độ trễ tail latency |

Phải tách **chi phí kiểm tra xem có khớp không** với **chi phí thực thi advice sau khi đã khớp**. Nếu advice gọi dịch vụ mạng, chi phí I/O có thể áp đảo phần predicate; nếu advice gần như rỗng trên một hot path, chính phần chọn điểm/interception lại trở nên đáng kể.

### 4.1. Mô hình chi phí gần đúng

Đối với một nhóm join point, có thể dùng mô hình giản lược:

```text
Total overhead xấp xỉ =
    chi phí chuẩn bị/weaving (phân bổ theo vòng đời)
  + số lần xem xét điểm * chi phí interception/kiểm tra tĩnh còn lại
  + số lần phải kiểm tra động * chi phí kiểm tra động trung bình
  + số lần khớp * chi phí advice trung bình
  + tác động phụ do cấp phát, đồng bộ, cache và I/O
```

Đây là **mô hình tư duy**, không phải công thức thời gian chính xác cho mọi công cụ. Hệ thống có thể tối ưu hoặc hợp nhất các bước, và chi phí thực tế phụ thuộc phân phối đầu vào cùng tải đồng thời.

Ví dụ giả định: một điều kiện tốn 100 ns mỗi lần và được đánh giá 1.000.000 lần mỗi giây sẽ tiêu thụ xấp xỉ 100 ms CPU mỗi giây (khoảng 0,1 CPU core tính lý tưởng), **chưa kể** overhead khác. Các con số chỉ nhằm chỉ ra tác động của tần suất; không phải benchmark của một công cụ AOP.

### 4.2. Chi phí theo số lần gọi khác chi phí theo số shadow

Một pointcut bao phủ 20 method executions hiếm khi chạy chưa chắc đắt hơn pointcut chỉ bao phủ một phương thức được gọi liên tục.

Để dự đoán có cơ sở, cần biết:

1. Có bao nhiêu điểm có thể bị can thiệp?
2. Mỗi điểm được đi qua bao nhiêu lần dưới tải thực?
3. Bao nhiêu lần cần kiểm tra điều kiện runtime?
4. Tỷ lệ khớp thực tế là bao nhiêu?
5. Advice khớp tốn bao nhiêu CPU, cấp phát, I/O hoặc khóa?

Phép đo cần phân biệt **số điểm tĩnh**, **số invocation** và **số advice thực sự chạy**.

## 5. Short-circuit và thứ tự điều kiện

Khi ngôn ngữ/công cụ pointcut hỗ trợ tổ hợp logic, có thể mô tả điều kiện dạng:

```text
isTransferOperation AND isVipAccount AND amountOverThreshold
```

Đây là **mã giả**, không phải một DSL pointcut cụ thể.

Trong các ngôn ngữ có đánh giá ngắn mạch, nếu điều kiện đầu sai thì các điều kiện sau có thể không cần đánh giá. Đưa bộ lọc **rẻ, có khả năng loại nhiều trường hợp và không phụ thuộc side effect** lên trước có thể giảm công việc.

Tuy nhiên cần thận trọng:

- Không phải mọi công cụ AOP đều cam kết đánh giá các pointcut con theo đúng **thứ tự văn bản** mà người viết nhập.
- Một engine có thể tự sắp xếp/ tối ưu các điều kiện theo metadata và semantics được phép.
- Nếu logic phụ thuộc vào side effect của một predicate, việc tối ưu hoặc thay đổi thứ tự có thể gây lỗi.
- `AND` và `OR` phải được nhóm đúng ý bằng dấu ngoặc, đặc biệt khi kết hợp loại trừ.

Vì thế, **đừng dùng pointcut như một workflow bắt buộc chạy từng kiểm tra theo thứ tự**. Điều kiện chọn điểm nên thuần, xác định được và không dựa vào số lần engine gọi predicate.

### 5.1. Ví dụ tối ưu hợp lý

Giả sử yêu cầu là chỉ audit khoản chuyển giá trị lớn ở một nhóm tài khoản. Một thiết kế có thể:

- Loại các phương thức không phải `transfer` từ giai đoạn cấu trúc.
- Kiểm tra kiểu/định dạng đối số cần thiết tại thời điểm chạy.
- Kiểm tra ngưỡng bằng phép so sánh đơn giản.
- Chỉ sau khi khớp mới thực thi phần audit có chi phí cao.

Nếu ngữ nghĩa chính sách cho phép và dữ liệu đã có tại thời điểm kiểm tra, đây là cách giảm tần suất xử lý đắt tiền mà vẫn bảo toàn tập điểm mong muốn.

## 6. Điều kiện theo đối tượng, tham số và luồng điều khiển

Một số mô hình AOP hỗ trợ chọn điểm dựa trên **kiểu đối tượng**, **đối số thực tế** hoặc **trạng thái luồng thực thi**. Ví dụ, **AspectJ** có các designator như `args`, `this`, `target`, `cflow` với ngữ nghĩa riêng của công cụ.

Ví dụ minh họa **cú pháp AspectJ**, không phải Java độc lập và không phải ngữ pháp chung cho mọi giải pháp:

```aspectj
execution(* example.TransferService.transfer(..))
    && args(java.lang.String, long)
```

Phần `execution` xác định dạng method execution theo mẫu. Phần `args` xét hình dạng/kiểu đối số theo ngữ nghĩa của designator. Cần phân biệt **kiểu đối số** với điều kiện **giá trị số tiền vượt ngưỡng**, vì ví dụ trên tự nó không diễn đạt phép so sánh `amount > 1000`.

Một ví dụ khác:

```aspectj
cflow(execution(* example.BatchService.runBatch(..)))
```

`cflow` chọn theo **phạm vi luồng điều khiển động** phù hợp với một điểm xuất phát. Nó có thể cần cơ chế theo dõi ngữ cảnh hơn một mẫu chỉ dựa trên chữ ký tĩnh. Tuy nhiên, chi phí và cách triển khai thực tế cần đo trên công cụ được dùng; không được suy rằng một designator có overhead cố định trên mọi môi trường.

### 6.1. Khác nhau giữa `within` và điều kiện theo luồng chạy

- Một điều kiện theo vị trí mã như `within` (trong ngữ nghĩa công cụ có designator này) mô tả **nơi join point được định nghĩa**.
- Một điều kiện như `cflow` mô tả **lần chạy có nằm trong một luồng điều khiển cụ thể** hay không.

Một lời gọi tới phương thức ở thư viện khác có thể xảy ra bên trong luồng thực thi của `runBatch`, mặc dù phần mã thư viện không được định nghĩa trong kiểu `BatchService`. Vì vậy hai loại điều kiện có thể chọn những tập join point khác nhau.

### 6.2. Phép kiểm tra trạng thái mutable

Giả sử điều kiện động đọc `policy.isEnabled(accountId)`. Nếu trạng thái chính sách có thể đổi đồng thời, kết quả có thể khác giữa hai invocation hoặc giữa hai giai đoạn của cùng một thao tác.

Nếu dùng trạng thái runtime trong điều kiện quan trọng, cần quyết định:

1. Thời điểm nào là ranh giới quyết định chính sách?
2. Dữ liệu đọc có nhất quán hoặc có snapshot tương ứng không?
3. Nếu dữ liệu thay đổi ngay sau lúc kiểm tra, điều gì phải xảy ra?
4. Khi đọc cấu hình thất bại, nên từ chối, cho phép hay báo lỗi theo hợp đồng?

Đây là vấn đề **tính nhất quán và thời điểm kiểm tra**, không chỉ hiệu năng.

## 7. Predicate động nên có tính chất gì?

Một điều kiện động tốt thường là:

- **Thuần về ý nghĩa:** không thay đổi dữ liệu nghiệp vụ chỉ để kiểm tra có khớp.
- **Dễ quyết định:** cùng một snapshot ngữ cảnh và chính sách cho kết quả nhất quán.
- **Rẻ tương đối với điểm can thiệp:** tránh I/O nặng trên đường gọi nóng khi có cách thiết kế khác.
- **Chịu được dữ liệu biên:** null, số âm, kiểu không phù hợp, đối tượng bị thiếu metadata.
- **An toàn đồng thời:** không dùng trạng thái mutable chung không bảo vệ.
- **Có thể kiểm thử độc lập:** có đầu vào/đầu ra rõ và có thể dựng được các trường hợp.
- **Không tạo vòng lặp can thiệp:** logic predicate/advice không vô ý kích hoạt lại cùng pointcut.

**Không nên đánh đồng “thuần” với “luôn được engine gọi đúng một lần”.** Nếu predicate có side effect như tăng bộ đếm nghiệp vụ hoặc ghi dữ liệu, số lần gọi do engine quyết định có thể làm thay đổi hệ thống theo cách khó dự đoán.

### 7.1. Vì sao không nên truy vấn dữ liệu ngoài trong mọi lần kiểm tra?

Giả sử kiểm tra `accountIsRisky(accountId)` gọi dịch vụ qua mạng ở mỗi invocation. Ngay cả khi chỉ 1% invocation nhận advice, 100% điểm tiềm năng có thể phải chịu chi phí mạng trước khi biết chúng không khớp.

Một thiết kế thay thế có thể chuyển dữ liệu chính sách tới một cấu trúc local được làm mới theo cơ chế rõ ràng, hoặc đặt việc kiểm tra ở ranh giới nghiệp vụ có thể quản lý được. Nhưng khi dùng cache phải xem xét **thời hạn hiệu lực, khả năng lỗi thời và yêu cầu nhất quán**; giảm latency không được âm thầm thay đổi quyết định chính sách.

## 8. Không thể cache mọi điều kiện động theo chữ ký

Một lỗi tối ưu hóa phổ biến là ghi nhớ kết quả `selected=true` cho một phương thức rồi áp dụng cho mọi lần gọi sau.

Nếu pointcut phụ thuộc `amount`, hai lần `transfer("A",50)` và `transfer("A",5000)` có thể cho kết quả khác nhau dù **cùng chữ ký**. Cache theo tên/chữ ký làm sai tập được chọn.

Các phân biệt cần thiết:

- **Metadata tĩnh:** có thể chia sẻ hoặc cache theo định danh kiểu/điểm khi hệ thống cho phép.
- **Kết quả kiểm tra động:** gắn với invocation hoặc tập dữ liệu làm nên quyết định.
- **Điều kiện ngữ cảnh theo control flow:** thường phụ thuộc ngăn xếp/luồng tác vụ hiện tại, không chỉ tham số.
- **Quy tắc thay đổi theo thời gian:** có thể phải có phiên bản chính sách và chiến lược invalidation.

Nếu caching thực sự cần thiết, phải chứng minh khóa cache chứa đầy đủ dữ liệu quyết định, có semantics về hết hạn/thay đổi và có kiểm thử chứng minh không lẫn giữa invocation.

## 9. Khả năng kiểm thử: cần kiểm tra những lớp nào?

Kiểm thử điều kiện động không dừng ở việc một predicate trả `true` cho vài đối số. Có ít nhất bốn lớp cần phân biệt:

1. **Predicate unit test:** logic theo args, kiểu runtime, ngữ cảnh hoặc trạng thái.
2. **Pointcut matching test:** mẫu tĩnh chọn đúng loại join point và tập vị trí phù hợp.
3. **Weaving/interception integration test:** đường gọi thực sự đi qua điểm có advice.
4. **Behavior test:** kết quả/ngoại lệ, thứ tự advice và side effect nghiệp vụ được bảo toàn theo yêu cầu.

Bảng:

| Lớp kiểm thử | Câu hỏi xác minh | Ví dụ lỗi |
| --- | --- | --- |
| Unit predicate | Đúng điều kiện biên? | Dùng `>=` thay cho `>` |
| Matching tĩnh | Đúng phương thức và loại điểm? | Chọn quá rộng vì wildcard |
| Integration | Điểm có được can thiệp thật? | Self-invocation bỏ qua proxy |
| Hành vi | Caller nhận đúng kết quả/ngoại lệ? | Advice nuốt lỗi hoặc gọi `proceed` hai lần |
| Hiệu năng | Latency và allocation có đạt yêu cầu? | Predicate gây GC hoặc I/O quá lớn |
| Đồng thời | Không trộn context giữa các lần gọi? | Dùng chung biến `currentAmount` |

Cần xác định **đáp án đúng độc lập với chính pointcut**. Nếu “tập điểm phải chọn” được tính bằng cách chạy chính pointcut cần kiểm tra, bài kiểm thử chỉ xác nhận nó nhất quán với bản thân, không phát hiện được sai phạm vi.

## 10. Các trường hợp biên cho điều kiện theo giá trị

Với yêu cầu “chỉ audit khoản chuyển có `amount > 1000` và `accountId` bắt đầu bằng `VIP-`”, nên kiểm thử:

| Ngữ cảnh | Có chọn? | Vì sao |
| --- | --- | --- |
| `("VIP-1",1001)` | Có | Vượt ngưỡng và đúng nhóm |
| `("VIP-1",1000)` | Không | Bằng ngưỡng, không lớn hơn |
| `("VIP-1",999)` | Không | Dưới ngưỡng |
| `("STD-1",9000)` | Không | Sai nhóm |
| `("VIP-",5000)` | Tùy hợp đồng tên | Prefix hợp cú pháp nhưng có thể thiếu mã thực |
| `(null,5000)` | Không hoặc lỗi được quy định | Không được gây `NullPointerException` ngoài ý muốn |
| `("VIP-1",-1)` | Không | Giá trị âm không vượt ngưỡng |
| Kiểu đối số không đúng | Theo hợp đồng công cụ/ứng dụng | Kiểm tra kiểu an toàn |
| Method execution khác tên | Không | Phải trượt bộ lọc tĩnh |

**Không được biến các ca giả định thành quy tắc nghiệp vụ phổ quát.** Ví dụ chính sách có thể yêu cầu null là lỗi bắt buộc thay vì “không chọn”. Điều quan trọng là **ghi rõ hợp đồng** rồi kiểm thử đúng hợp đồng ấy.

### 10.1. Dương tính và âm tính đều quan trọng

Nếu chỉ kiểm thử `("VIP-1",1001)` và thấy advice chạy, chưa thể biết pointcut có vô tình chạy với `("STD-1",9000)` hay không. Một bộ kiểm thử đầy đủ cần cả:

- **True positive:** điểm phải được chọn và đã được chọn.
- **False positive:** điểm không thuộc yêu cầu nhưng bị chọn.
- **False negative:** điểm cần chọn nhưng bị bỏ sót.
- **True negative:** điểm ngoài phạm vi và không được chọn.

Với advice có thể kiểm tra quyền hoặc thay đổi hành vi, FP và FN có thể tạo hậu quả khác nhau và phải được đánh giá theo mức độ rủi ro.

## 11. Ví dụ Java 17 chạy được: lọc tĩnh trước, kiểm tra động sau

Java thông thường không có một parser pointcut AOP tích hợp. Ta có thể dùng chương trình sau để **mô phỏng thứ tự lựa chọn**, đếm số lần đánh giá điều kiện và quan sát những lần được chọn.

Ví dụ chỉ là **Java thuần minh họa thuật toán chọn điểm**; nó không cung cấp weaving và không thay thế công cụ AOP thật. Điều kiện được viết trong mã nhằm minh họa quan hệ giữa chi phí đánh giá và số lần advice được chọn.

Lưu thành tệp `DynamicConditionDemo.java`:

```java
public class DynamicConditionDemo {

    record Invocation(String operation, String accountId, long amount) {}

    static final class Counters {
        int staticRejected;
        int dynamicChecks;
        int adviceRuns;
    }

    static boolean staticCandidate(Invocation call) {
        return "transfer".equals(call.operation());
    }

    static boolean dynamicMatches(Invocation call, Counters counters) {
        counters.dynamicChecks++;
        return call.accountId() != null
                && call.accountId().startsWith("VIP-")
                && call.amount() > 1000;
    }

    static void executeBusiness(Invocation call) {
        System.out.println("business:" + call.operation()
                + ":" + call.accountId() + ":" + call.amount());
    }

    static void dispatch(Invocation call, Counters counters) {
        if (!staticCandidate(call)) {
            counters.staticRejected++;
            executeBusiness(call);
            return;
        }

        if (dynamicMatches(call, counters)) {
            counters.adviceRuns++;
            System.out.println("advice:audit:" + call.accountId()
                    + ":" + call.amount());
        }

        executeBusiness(call);
    }

    public static void main(String[] args) {
        Counters counters = new Counters();

        dispatch(new Invocation("transfer", "VIP-7", 1500), counters);
        dispatch(new Invocation("transfer", "STD-8", 9000), counters);
        dispatch(new Invocation("lookup", "VIP-9", 5000), counters);
        dispatch(new Invocation("transfer", "VIP-1", 1000), counters);
        dispatch(new Invocation("transfer", null, 4000), counters);

        if (counters.staticRejected != 1
                || counters.dynamicChecks != 4
                || counters.adviceRuns != 1) {
            throw new AssertionError("unexpected selection counts");
        }

        System.out.println("summary:staticRejected="
                + counters.staticRejected
                + ",dynamicChecks=" + counters.dynamicChecks
                + ",adviceRuns=" + counters.adviceRuns);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac DynamicConditionDemo.java
java DynamicConditionDemo
```

Đầu ra **xác định**:

```text
advice:audit:VIP-7:1500
business:transfer:VIP-7:1500
business:transfer:STD-8:9000
business:lookup:VIP-9:5000
business:transfer:VIP-1:1000
business:transfer:null:4000
summary:staticRejected=1,dynamicChecks=4,adviceRuns=1
```

### 11.1. Đọc kết quả

- Có **5 lần gọi** mô phỏng.
- `lookup` không qua bộ kiểm tra động vì trượt điều kiện tĩnh, nên `staticRejected=1`.
- Bốn lần `transfer` phải qua điều kiện động, nên `dynamicChecks=4`.
- Chỉ `transfer("VIP-7",1500)` đạt cả prefix và ngưỡng, nên `adviceRuns=1`.
- Mọi thao tác vẫn chạy logic nghiệp vụ `executeBusiness` vì ví dụ chỉ mô phỏng advice quan sát; không từ chối thực thi.
- `null` được xử lý có chủ đích, tránh lỗi null ngoài ý muốn.

Các bộ đếm phản ánh **logic mô phỏng cụ thể**, không phải số lần predicate sẽ được một engine AOP bất kỳ gọi. Một công cụ thật có thể có chiến lược tối ưu khác.

### 11.2. Vì sao ví dụ không phải benchmark?

Mã in ra console, tạo record và chạy chỉ năm lần. Đo thời gian trực tiếp trên chương trình này chủ yếu phản ánh thời gian khởi động JVM, JIT chưa ổn định và I/O console. Nó phù hợp để **kiểm chứng kết quả lựa chọn**, nhưng không đủ để kết luận overhead AOP là bao nhiêu nanosecond hay phần trăm.

Để đo hiệu năng có ý nghĩa, phải dựng workload đại diện, tách chi phí instrumentation/advice và kiểm soát warm-up, tải đồng thời, phân bổ bộ nhớ cũng như môi trường chạy.

## 12. Kiểm thử predicate độc lập với weaving

Để giảm độ khó gỡ lỗi, nên tách logic chính sách đơn giản thành thành phần có thể kiểm thử độc lập trước khi đưa vào điểm can thiệp AOP.

Ví dụ một predicate tương ứng với quy tắc:

```java
static boolean requiresAudit(String accountId, long amount) {
    return accountId != null
            && accountId.startsWith("VIP-")
            && amount > 1000;
}
```

Đây là **mảnh mã Java minh họa**, không phải chương trình độc lập có `main`.

Có thể kiểm tra predicate bằng bộ giá trị biên, bao gồm null, giá trị đúng ngưỡng và sát ngưỡng. Sau đó cần **một lớp kiểm thử tích hợp riêng** để chứng minh công cụ AOP truyền đúng args/ngữ cảnh vào predicate và advice chỉ chạy tại đúng những join point.

Không nên gộp tất cả logic vào biểu thức có nhiều điều kiện không quan sát được, rồi chỉ kiểm tra kết quả cuối cùng. Khi có lỗi, ta cần biết:

1. Điểm có thuộc tập tĩnh không?
2. Ngữ cảnh động được lấy đúng chưa?
3. Predicate có trả đúng giá trị không?
4. Advice có chạy đúng số lần không?
5. Nghiệp vụ còn giữ đúng hợp đồng không?

### 12.1. Lập bảng quyết định độc lập

Một bảng ca kiểm thử nên xuất phát từ yêu cầu thực tế:

```text
RULE: AUDIT iff operation == transfer AND account begins VIP-
      AND amount > 1000.

POSITIVE:
  transfer(VIP-1,1001)
  transfer(VIP-2,5000)

NEGATIVE:
  lookup(VIP-1,5000)
  transfer(STD-1,5000)
  transfer(VIP-1,1000)
  transfer(null,5000)
```

Đây là **mẫu kiểm thử bằng văn bản**, không phải output chạy tự động. Nếu yêu cầu thay đổi, sửa bảng quyết định trước rồi cập nhật pointcut/advice cho khớp.

## 13. Kiểm thử ngữ cảnh đối tượng và kiểu runtime

Một số điều kiện động xét đối tượng đích (`target`) hoặc đối tượng hiện hành (`this` trong mô hình công cụ). Với đa hình, kiểu khai báo và kiểu runtime có thể khác nhau.

Ví dụ:

```java
interface PaymentGateway {
    void charge(long amount);
}

final class RemoteGateway implements PaymentGateway {
    @Override
    public void charge(long amount) {}
}
```

Đây là **đoạn khai báo minh họa**, chưa là ứng dụng độc lập. Nếu code gọi qua biến kiểu `PaymentGateway` nhưng đích runtime là `RemoteGateway`, điều kiện dựa trên kiểu khai báo có thể khác điều kiện dựa trên đối tượng runtime.

Các ca nên kiểm tra:

- Lời gọi trên nhiều lớp thực hiện cùng giao diện.
- Một subtype được thêm sau khi pointcut được viết.
- Lời gọi qua proxy hoặc đối tượng trung gian.
- Lời gọi trực tiếp tới đích.
- Phương thức overload/override liên quan.
- Trường hợp không có đối tượng instance (ví dụ một số điểm tĩnh), nếu loại join point hỗ trợ.

**Đừng tự suy rằng `this` và `target` luôn đồng nhất.** Ngữ nghĩa phụ thuộc công cụ và loại join point; một lớp trung gian có thể khiến đối tượng bên gọi, proxy và đối tượng đích khác nhau.

## 14. Kiểm thử điều kiện theo control flow

Một chính sách có thể yêu cầu advice chỉ áp dụng khi thao tác xảy ra **bên trong luồng thực thi** của một công việc lớn.

Ví dụ:

```text
runBatch()
   |
   +-- stepA() ----> repository.save()
   |
   +-- stepB() ----> repository.save()

interactiveRequest() --> repository.save()
```

Nếu mục tiêu là quan sát `save` khi đang ở trong `runBatch`, cần xác định rõ liệu “trong luồng” nghĩa là:

- Lời gọi lồng nhau đồng bộ theo call stack.
- Công việc bất đồng bộ do batch khởi phát rồi chạy ở thread khác.
- Một trace/correlation ID được truyền giữa các tác vụ.

Ba cách hiểu này **không tự tương đương**. Một điều kiện theo call stack không tự động theo tác vụ sang mọi luồng khác.

Kiểm thử nên bao gồm:

1. `save` được gọi đồng bộ từ `runBatch` — mong muốn được chọn.
2. `save` từ một yêu cầu tương tác độc lập — không được chọn.
3. `runBatch` lồng trong `runBatch` — ngữ cảnh bắt đầu/kết thúc phải cân bằng.
4. `runBatch` ném ngoại lệ — trạng thái control-flow phải được giải phóng.
5. Batch chuyển công việc sang thread khác — xác minh phạm vi mong muốn và ngữ nghĩa mà công cụ hỗ trợ.

Nếu tự hiện thực tracking, không được chỉ bật một cờ `boolean inBatch` toàn cục mà không phân biệt thread/lần gọi; điều đó có thể làm tất cả yêu cầu đồng thời bị đánh dấu sai.

## 15. Đồng thời, đệ quy và reentrancy

Điều kiện động thường cần dữ liệu theo từng invocation hoặc từng luồng điều khiển. Điều này tạo các trường hợp phức tạp khi ứng dụng đa luồng, đệ quy hoặc advice tự kích hoạt lại những điểm liên quan.

### 15.1. Đồng thời

Giả sử cùng một phương thức `transfer` chạy trên hai thread:

```text
Thread A: transfer("VIP-1",5000) --> selected
Thread B: transfer("STD-2",9000) --> not selected
```

Nếu aspect lưu biến instance `currentAccount` dùng chung rồi thay ở mỗi lần gọi, điều kiện có thể đọc dữ liệu của thread khác. Nên dùng ngữ cảnh gắn với invocation, giá trị bất biến hoặc cơ chế đồng bộ/truyền ngữ cảnh phù hợp.

### 15.2. Đệ quy

Một phương thức đệ quy có thể tạo nhiều lần xuất hiện cùng join point đang lồng nhau. Nếu điều kiện động phụ thuộc vào độ sâu, cần xác định ngữ nghĩa rõ và giảm độ sâu đúng khi thoát, kể cả trên nhánh ngoại lệ.

Sử dụng một biến `currentDepth` dùng chung không bảo vệ cho nhiều thread là không an toàn; một biến theo thread cũng chưa tự giải quyết việc truyền context qua ranh giới bất đồng bộ.

### 15.3. Advice tự kích hoạt lại advice

Nếu advice ghi log bằng cách gọi phương thức cũng khớp pointcut, có thể xuất hiện vòng gọi lặp ngoài ý muốn:

```text
advice -> logger.log() -> join point log được chọn -> advice -> ...
```

Cần giới hạn phạm vi pointcut, lựa chọn điểm logging ngoài tập cần can thiệp hoặc sử dụng cơ chế ngăn reentrancy thích hợp. Đừng chỉ giải quyết bằng một biến cờ global vì có thể chặn nhầm các invocation độc lập.

## 16. Bất đồng bộ: method return khác completion

Một phương thức bất đồng bộ có thể trả về `CompletableFuture<Result>` trước khi công việc hoàn tất.

```text
Caller
  |
  |-- startJob() ------> advice quanh method execution
  |                     -> tạo Future
  |<-- Future ---------- method đã trả về
  |
  |       ... công việc chạy ở thời điểm/luồng khác ...
  |
  +<-- Future complete(result/error)
```

Nếu điều kiện động dựa trên args của `startJob`, nó có thể được kiểm tra ở lúc gọi. Nhưng nếu chính sách dựa trên **kết quả công việc**, thông tin đó chưa tồn tại khi phương thức chỉ mới trả Future.

Một advice quan sát “method returned normally” không thể mặc định kết luận “job completed successfully”. Cần xác định đúng ranh giới hoàn tất và cách mang ngữ cảnh từ invocation ban đầu tới completion callback nếu chính sách yêu cầu.

Kiểm thử nên có:

- Future hoàn tất bình thường.
- Future hoàn tất thất bại.
- Future bị hủy.
- Completion xảy ra trên thread khác.
- Nhiều Future chạy đồng thời.
- Ngữ cảnh của từng request được truyền đúng và giải phóng sau completion.

Chi phí theo dõi context có thể bao gồm cấp phát callback, lưu correlation ID hoặc quản lý vòng đời. Nó khác với chi phí predicate trên phương thức khởi tạo.

## 17. Lỗi từ predicate và chiến lược xử lý

Điều kiện động không phải lúc nào cũng chỉ trả `true` hoặc `false`. Việc đọc trạng thái, parsing hoặc gọi helper có thể ném lỗi.

Cần quyết định rõ theo hợp đồng:

| Tình huống | Câu hỏi thiết kế |
| --- | --- |
| Đối số null/không hợp lệ | Loại điểm, hay thất bại rõ ràng? |
| Chính sách runtime không khả dụng | Cho phép, từ chối, hay lỗi tới caller? |
| Predicate ném ngoại lệ | Lỗi có được truyền tiếp hay chuyển đổi? |
| Predicate quá chậm | Có timeout/budget không? |
| Dữ liệu thay đổi trong khi kiểm tra | Dùng snapshot/phiên bản nào? |
| Advice lỗi sau khi predicate khớp | Có che ngoại lệ nghiệp vụ gốc không? |

Với telemetry tùy chọn, việc ghi nhận thất bại có thể được xử lý khác với kiểm soát truy cập bắt buộc. **Không có chính sách fail-open/fail-closed đúng cho mọi aspect.** Việc chọn phải dựa vào mục tiêu nghiệp vụ và ranh giới tin cậy.

Quan trọng hơn: nếu kiểm soát truy cập chỉ dựa vào một điều kiện động ở các điểm AOP, cần chứng minh **mọi đường vào cần bảo vệ** thực sự đi qua cơ chế can thiệp. Một đường gọi trực tiếp bỏ qua proxy có thể khiến mọi phép kiểm tra predicate đều vô nghĩa.

## 18. Cách benchmark điều kiện động có cơ sở

Không nên kết luận “điều kiện động chậm” chỉ từ một lần `System.nanoTime()` quanh vài lệnh. JVM có warm-up, JIT, GC, biến động tải và rất nhiều yếu tố nhiễu.

Một kế hoạch đo phù hợp:

1. **Xác định câu hỏi:** muốn đo overhead của pointcut, của predicate hay của toàn bộ advice?
2. **Dựng các biến thể:** baseline không interception; có interception nhưng điều kiện luôn trượt; điều kiện khớp với advice nhẹ; điều kiện khớp với advice thật.
3. **Giữ workload đại diện:** đúng phân phối tham số, tỷ lệ khớp và tần suất các phương thức nóng.
4. **Kiểm soát JVM và môi trường:** phiên bản JDK, warm-up, CPU, heap, mức tải và GC.
5. **Dùng công cụ benchmark phù hợp:** JMH hữu ích cho microbenchmark Java; kiểm tra thực tế thêm bằng profiling/load test.
6. **Đo nhiều chiều:** throughput, p50/p95/p99 latency, allocation rate, GC, CPU và contention.
7. **Lặp lại và báo độ biến thiên:** không suy từ một con số duy nhất.
8. **Đối chiếu correctness:** một biến thể nhanh nhưng bỏ sót advice cần chạy không phải tối ưu thành công.

Một cách phân tích:

```text
baseline                             : không có cơ chế AOP
interception + always-false condition : chủ yếu đo đường chặn/kiểm tra
interception + simple dynamic condition: thêm chi phí predicate
interception + matching advice         : thêm chi phí hành vi bổ sung
```

Mô hình này chỉ có ý nghĩa nếu các biến thể thực sự so sánh cùng công việc và kết quả vẫn đúng. Một điều kiện luôn sai có thể được tối ưu khác một điều kiện động thật; cần diễn giải số đo cẩn trọng.

### 18.1. Tỷ lệ khớp ảnh hưởng số đo thế nào?

Nếu 99% lần gọi không khớp, phần đáng chú ý có thể là chi phí kiểm tra ở các lần bị loại. Nếu 90% lần gọi khớp và advice ghi log đồng bộ, phần advice có thể chi phối latency.

Vì vậy báo cáo benchmark nên kèm **match rate** và số invocation/giây. Một số đo chỉ có “ns/op” nhưng không nêu cấu hình lọc và tỷ lệ khớp khó áp dụng sang tải thực.

## 19. Cách cải thiện hiệu năng mà vẫn giữ tính đúng đắn

Các hướng cải thiện thường đáng cân nhắc:

- **Thu hẹp tập điểm tĩnh:** chỉ áp dụng điều kiện động tại những phương thức/thành phần thật sự có liên quan.
- **Dùng dữ liệu đã có:** tránh lấy lại metadata hoặc chuyển đổi đối số nhiều lần nếu có thể sử dụng an toàn.
- **Giữ predicate đơn giản, thuần và ít cấp phát:** tránh regex phức tạp, phản xạ lặp lại hoặc I/O không cần thiết trên hot path.
- **Tối ưu luồng chọn điểm theo hợp đồng công cụ:** không phụ thuộc vào thứ tự đánh giá ngoài những điều engine cam kết.
- **Giảm chi phí advice riêng biệt:** batch metric/log, chọn dữ liệu cần thiết và tránh chặn I/O không cần thiết.
- **Kiểm soát tần suất quan sát:** sampling có thể phù hợp với telemetry, nhưng không được dùng để làm rơi các lần audit bắt buộc.
- **Dùng cache có điều kiện:** chỉ khi khóa/phiên bản phản ánh đủ dữ liệu quyết định.
- **Kiểm tra lại coverage sau tối ưu:** tăng tốc không được sinh false negative hoặc false positive.

Một ví dụ trade-off: chuyển từ điều kiện theo giá trị động sang chọn theo annotation tĩnh có thể giảm phép kiểm tra runtime, nhưng chỉ đúng nếu **ý định chính sách thực sự có thể biểu diễn bằng metadata tĩnh**. Nếu chính sách cần phân biệt `amount=50` và `amount=5000` trên cùng một phương thức, annotation đơn độc không thay thế được điều kiện theo giá trị.

## 20. Những sai lầm thường gặp

**“Điều kiện động luôn chậm.”** Sai. Phép so sánh rẻ có thể không đáng kể; tần suất chạy, cách lấy context và advice mới quyết định tác động.

**“Pointcut không khớp thì không có chi phí.”** Chưa chắc. Hệ thống có thể phải chạy interceptor hoặc đánh giá một phần điều kiện trước khi biết nó không khớp.

**“Đặt điều kiện rẻ đầu biểu thức đảm bảo engine kiểm tra trước.”** Không phải cam kết chung của mọi DSL/công cụ. Có thể có tối ưu hoặc sắp xếp lại.

**“Cache kết quả theo tên phương thức sẽ tăng tốc an toàn.”** Sai nếu điều kiện phụ thuộc args, target, control flow hoặc trạng thái thay đổi.

**“Unit test predicate đủ chứng minh pointcut.”** Không. Cần cả kiểm thử loại join point, weaving/interception và đường thực thi.

**“Một lần thấy advice chạy chứng minh không có bỏ sót.”** Sai. Cần các ca âm tính, đường gọi khác và trường hợp biên.

**“Điều kiện theo thread tự động theo tác vụ bất đồng bộ.”** Không. Context có thể cần được truyền qua ranh giới tác vụ bằng cơ chế thích hợp.

**“Ghi lại mọi tham số để kiểm thử sẽ an toàn.”** Không. Có thể làm lộ dữ liệu nhạy cảm; nên dùng dữ liệu tổng hợp và chọn lọc trường ghi nhận.

**“Đo trên vòng lặp in console là benchmark AOP.”** Không. I/O và JVM startup làm sai lệch phép đo, chưa kể chương trình mô phỏng không có weaving thật.

**“Điều kiện dynamic khớp thì nghiệp vụ chắc chắn thực thi.”** Không. Advice bao quanh có thể thay đổi việc chuyển tiếp, và các advice khác có thể thay đổi luồng.

## 21. Bài tập tự kiểm tra

**Bài 1.** Một phương thức được gọi 2 triệu lần mỗi giây. Predicate đơn giản tốn trung bình 50 ns/lần. Tổng chi phí CPU lý tưởng cỡ nào?

```text
2.000.000 * 50 ns = 100.000.000 ns = 100 ms CPU mỗi giây.
```

Đây là ước lượng lý tưởng theo giả định, chưa tính interception, JIT, phân bổ và contention. Không coi nó là đo thực nghiệm.

**Bài 2.** Một bộ lọc theo chữ ký `transfer` đi qua 1.000 lần; 100 lần vượt ngưỡng. Có thể tiết kiệm 900 lần kiểm tra động không?

Không chỉ từ thông tin “100 lần vượt ngưỡng”, vì muốn biết lần nào vượt ngưỡng hệ thống có thể phải **kiểm tra cả 1.000 lần**. Có thể giảm công việc nếu tồn tại bộ lọc trước rẻ hơn hoặc metadata/cấu trúc phân biệt được các nhóm, nhưng phải giữ đúng kết quả.

**Bài 3.** Tại sao cached `selected=true` theo chữ ký `transfer(String,long)` có thể sai?

Vì lần gọi sau có số tiền, đối tượng hoặc trạng thái khác. Kết quả động không chỉ phụ thuộc chữ ký.

**Bài 4.** Predicate `amount > 1000` được unit test đầy đủ nhưng advice không chạy ở một lời gọi nội bộ. Cần kiểm tra đâu?

Kiểm tra cơ chế weaving/interception và đường gọi: nếu dùng proxy, self-invocation có thể bỏ qua proxy. Kiểm tra tiếp loại join point và các điều kiện khác của pointcut.

**Bài 5.** Nếu một công việc được gửi sang executor, `cflow` theo call stack của thread gọi có chắc áp dụng cho công việc ở thread mới không?

Không thể mặc định. Phải xác minh ngữ nghĩa của công cụ; chuyển công việc bất đồng bộ không tự động giữ cùng call stack hoặc mọi loại context.

**Bài 6.** Một điều kiện động gọi mạng mỗi khi đánh giá nhưng chỉ 1% lần gọi được advice. Vì sao vẫn có thể chậm?

Vì 99% lần trượt cũng có thể phải chờ kiểm tra mạng. Cần đo **chi phí chọn điểm**, không chỉ chi phí advice chạy khi khớp.

**Bài 7.** Khi tối ưu pointcut, ca kiểm thử nào đảm bảo không làm hỏng tính đúng đắn?

Cần đối chiếu tập dương/âm của chính sách, điều kiện biên, ngoại lệ, đồng thời/bất đồng bộ và kiểm thử tích hợp chứng minh đúng phạm vi weaving. Benchmark nhanh hơn mà thay đổi tập chọn là thất bại về correctness.

## 22. Checklist thực hành

Trước khi đưa pointcut có điều kiện động vào hệ thống:

1. [ ] Có mô tả rõ **lần thực thi nào cần được advice xử lý**.
2. [ ] Đã phân biệt **điều kiện tĩnh** và **điều kiện runtime**.
3. [ ] Đã xác nhận loại join point và phạm vi công cụ hỗ trợ.
4. [ ] Có ca unit test đúng/sai/biên/null cho predicate.
5. [ ] Có ca kiểm thử dương và âm cho tập join point.
6. [ ] Có kiểm thử tích hợp cho đường gọi trực tiếp, qua trung gian và nội bộ khi liên quan.
7. [ ] Có chính sách rõ cho ngoại lệ và dữ liệu runtime không khả dụng.
8. [ ] Có kiểm thử đồng thời/đệ quy/context nếu điều kiện phụ thuộc trạng thái.
9. [ ] Có kiểm thử ranh giới bất đồng bộ nếu dùng context hoặc kết quả task.
10. [ ] Đã đo overhead trên tải phù hợp và tách chi phí predicate khỏi advice.
11. [ ] Không dùng caching, sampling hoặc tối ưu khác làm sai tập điểm bắt buộc.
12. [ ] Có quy tắc tránh log dữ liệu nhạy cảm và vòng gọi tái nhập không mong muốn.

**Kết luận:** điều kiện động giúp pointcut chính xác theo ngữ cảnh của từng invocation, đổi lại có thể yêu cầu kiểm tra runtime và làm tăng số trường hợp cần kiểm thử. Thiết kế tốt kết hợp **lọc cấu trúc tĩnh phù hợp**, **predicate động có hợp đồng rõ**, **kiểm thử trên đường thực thi thật** và **phép đo hiệu năng có cơ sở**. Không đánh đổi tính đúng đắn của phạm vi chỉ để có biểu thức ngắn hoặc số đo nhanh hơn.
