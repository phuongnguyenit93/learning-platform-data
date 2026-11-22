# Chọn thời điểm dệt theo yêu cầu hệ thống

## 1. Bài toán: dệt vào lúc nào, để đáp ứng yêu cầu gì?

Trong **Aspect-Oriented Programming (AOP)**, **weaving** là quá trình kết hợp phần hành vi của aspect với chương trình tại những **join point** được mô hình AOP hỗ trợ và được **pointcut** lựa chọn. Việc kết hợp có thể được thực hiện khi xây dựng mã, sau khi biên dịch nhưng trước khi triển khai, lúc class được nạp, hoặc bằng một cơ chế can thiệp lúc chương trình đang chạy. Mỗi thời điểm cho ta quyền kiểm soát, phạm vi, chi phí và rủi ro khác nhau.

Khi thiết kế một hệ thống cần AOP, câu hỏi đúng không phải chỉ là “compile-time weaving tốt hơn hay runtime weaving tốt hơn?”, mà là:

> **Những loại điểm nào bắt buộc phải can thiệp, công cụ đang dùng có thực hiện được ở thời điểm nào, ai kiểm soát artifact/loader/runtime, yêu cầu hiệu năng và vận hành ra sao, và bằng chứng nào chứng minh hệ thống thực sự đã được dệt đúng?**

Một cơ chế phù hợp cho một ứng dụng Java được build và triển khai nguyên khối chưa chắc phù hợp với ứng dụng plugin có nhiều classloader, môi trường khởi tạo linh hoạt, native executable, hoặc nơi không thể đụng vào bytecode của dependencies.

### Bạn sẽ học được gì?

1. Phân biệt **source/compile-time weaving**, **post-compile/binary weaving**, **load-time weaving**, **runtime instrumentation/retransformation** và **proxy/decorator interception**.
2. Hiểu khác biệt giữa **thời điểm kết hợp hành vi**, **thời điểm kích hoạt advice** và **thời điểm runtime xảy ra join point**.
3. Đánh giá trade-off: kiểm soát artifact, khả năng thay đổi chính sách, classloader/module, startup, build complexity, runtime overhead, rollback và bảo mật.
4. Chọn một chiến lược bằng **ma trận yêu cầu**, không dựa trên lời quảng cáo hay tên gọi của kỹ thuật.
5. Hiểu các giới hạn: method call khác method execution; proxy không tự bao phủ self-invocation; không phải mọi JVM runtime transformer có thể sửa tùy ý class đã nạp.
6. Thiết kế quy trình QA chứng minh **phạm vi dệt**, **pointcut matched**, **advice runtime**, cùng ca negative/bypass.
7. Chạy ví dụ Java 17 so sánh **decorator lắp ghép tường minh** với **dynamic proxy tạo khi chạy** mà không nhầm chúng với bytecode weaving.

Bài tập trung vào AOP **nói chung**, gồm cả nguyên tắc cơ bản và các cân nhắc kiến trúc nâng cao. Không có một cú pháp cấu hình weaving chung cho mọi công cụ/ngôn ngữ.

## 2. Bốn khái niệm cần phân biệt trước khi chọn thời điểm

### 2.1. Join point là sự kiện hoặc điểm được mô hình hóa, không phải chỉ một dòng mã

Tùy mô hình AOP, join point có thể là method execution, method call, constructor execution, field access hoặc những sự kiện khác. Ví dụ một call site trong vòng lặp có thể gây ra nhiều lượt method execution.

Phải hỏi công cụ hỗ trợ **loại join point** cần thiết trước khi hỏi công cụ thực hiện weaving vào lúc nào. Nếu kỹ thuật chỉ có khả năng chặn interface invocation, thay đổi thời điểm tạo proxy không tự khiến nó chặn được mọi field access.

### 2.2. Pointcut là quy tắc chọn, weaving là cách kết hợp

Một pointcut có thể mô tả “mọi execution của method được đánh dấu `@Observed`”. Nhưng có marker và pointcut khớp không đủ: class phải nằm trong phạm vi công cụ có thể xử lý, aspect được kích hoạt, artifact có hook, và đường runtime thực sự đến điểm đó.

```text
Class/artifact trong phạm vi công cụ có thể dệt?
   |
   +-- không --> không có hook từ cơ chế đó
   |
   +-- có ----> join-point kind có được hỗ trợ?
                   |
                   +-- không --> không chọn được loại điểm đó
                   |
                   +-- có ----> pointcut và điều kiện có khớp?
                                   |
                                   +-- không --> không có advice tương ứng
                                   |
                                   +-- có ----> runtime có occurrence?
                                                   |
                                                   +-- không --> advice không chạy
                                                   |
                                                   +-- có --> advice có thể kích hoạt
```

Không suy ra advice đã chạy chỉ vì một công cụ liệt kê class đã biến đổi; cũng không suy ra weaving thất bại chỉ vì chương trình test chưa từng đi qua điểm đã chọn.

### 2.3. “Dệt lúc runtime” có nhiều nghĩa khác nhau

Cụm “runtime AOP” thường bị dùng rộng, có thể chỉ:

- **Proxy/wrapper** được tạo khi chạy và nhận lời gọi qua proxy.
- **Load-time weaving** khi class vừa được định nghĩa bởi loader.
- **Instrumentation/retransformation** với class đã load, nếu runtime và công cụ hỗ trợ.
- **Các hook do compiler chèn từ trước** nhưng được bật/tắt bằng điều kiện runtime.
- **Cơ chế dynamic dispatch** hoặc interceptor trong framework.

Đây không phải cùng cơ chế. Chúng khác nhau ở **đơn vị bị tác động**, **điểm có thể chặn**, **khả năng tháo hook**, **quyền cấu hình** và **chi phí**.

### 2.4. Phân biệt thời điểm “cài hook” với thời điểm “hook được gọi”

Một method được weave ở build time **không có nghĩa advice chạy lúc build**. Build chỉ kết hợp code hoặc tạo artifact chứa hook; khi chương trình chạy đến join point, advice mới được thực thi.

Ngược lại, runtime proxy được tạo khi chương trình chạy nhưng handler cũng chỉ chạy **khi caller gọi qua proxy**. Không phải việc tạo proxy đã thực hiện advice nghiệp vụ.

## 3. Bức tranh các chiến lược phổ biến

| Chiến lược | Khi kết hợp hành vi | Đơn vị bị xử lý | Cần lưu ý |
| --- | --- | --- | --- |
| **Source-time / compile-time weaving** | Trong pipeline biên dịch hoặc biến đổi source/IR. | Source, AST/IR hoặc code đầu ra. | Cần tích hợp build/compiler; artifact thường được kiểm chứng trước chạy. |
| **Post-compile / binary weaving** | Sau compile, trước package/deploy hoặc trước chạy. | Bytecode/binary đã biên dịch. | Có thể biến đổi artifact từ bước khác nhưng phải kiểm soát binary và tương thích. |
| **Load-time weaving** | Khi class/module được runtime loader đưa vào sử dụng. | Định nghĩa class sắp load. | Phụ thuộc loader, thứ tự agent, quyền runtime và thời điểm đăng ký transformer. |
| **Runtime retransformation/redefinition** | Sau khi class đã load, nếu API/runtime cho phép. | Một số class đã có trong process. | Có ràng buộc về loại thay đổi, quyền attach/agent, trạng thái đang chạy và rollback. |
| **Runtime proxy/decorator** | Khi object hoặc wrapper được tạo/lắp ghép. | Object reference và những lời gọi đi qua wrapper. | Không đòi thay đổi bytecode của target, nhưng tập join point và đường gọi thường hẹp. |

**Điểm quan trọng:** Đây là phân loại kiến trúc, không phải xếp hạng chất lượng. Một chương trình có thể kết hợp nhiều kỹ thuật. Phần “compile-time” của một hệ thống có thể phát sinh wrapper thay vì chèn mọi hook vào method body; phải xem điều gì thực sự được tạo và giới hạn join-point model.

## 4. Dệt ở thời điểm source/compile-time

### 4.1. Cơ chế khái quát

Một công cụ có thể phân tích source, AST, intermediate representation hoặc cấu trúc compiler, tìm những điểm phù hợp, rồi sinh mã đã kết hợp advice.

```text
Source + mô tả aspect/pointcut
          |
          v
Compiler / source transformer
          |
          v
Artifact đã kết hợp logic can thiệp
          |
          v
Deploy -> runtime thực thi hook
```

Đối với phần lớn pipeline được kiểm soát chặt chẽ, kết quả weaving có thể được xem là **một phần của sản phẩm build**. Có thể kiểm chứng trong CI, ký artifact, chạy test và triển khai chính xác binary đã được đánh giá.

### 4.2. Ưu điểm thường có

- **Có cơ hội phát hiện lỗi sớm:** công cụ có thể báo một số lỗi matching, type/visibility hoặc transform trước triển khai.
- **Tái lập artifact:** cùng source, dependency, compiler, flags và rule có thể tạo ra đầu ra được version hóa, kiểm thử, ký và rollout.
- **Không bắt buộc chờ runtime classloading để chèn mọi hook:** một phần việc phân tích/biến đổi được hoàn tất trước khởi động.
- **Dễ đối chiếu phạm vi:** có thể kiểm tra mã sau biến đổi, danh sách join-point shadow/hook nếu công cụ hỗ trợ.
- **Phù hợp chính sách không cho phép runtime attach agent:** vì logic cần thiết có thể nằm sẵn trong artifact.

Không nên hứa “compile-time weaving luôn cho runtime overhead bằng 0”. Khi join point xảy ra, advice vẫn chạy và làm việc. Một số cơ chế có thêm kiểm tra động, cấp phát hoặc I/O; overhead thực tế phải đo.

### 4.3. Đánh đổi và rủi ro

- Cần quyền điều chỉnh **build pipeline**; khó hơn nếu chỉ có một binary đóng, không có source hoặc không được phép thay đổi bước build.
- Thời gian build, cache, incremental build và khả năng tái lập có thể bị ảnh hưởng.
- Nếu thay đổi aspect/pointcut thường xuyên, có thể cần **rebuild + redeploy**.
- Source/generated code do compiler khác sinh ra có thể không nằm trong transformer đã chọn.
- Nhiều compiler plugin có thể xung đột về thứ tự hoặc cấu trúc AST/IR.
- Native image/AOT và optimizer có thể tạo yêu cầu riêng; không tự cho rằng mọi công cụ source weaving tương thích.

### 4.4. Khi nên cân nhắc

Phù hợp khi hệ thống:

- Có quy trình build/release tập trung và có thể phát hành artifact đã qua QA.
- Muốn kiểm soát chặt thay đổi mã và không muốn agent tùy ý biến đổi class trong production.
- Không cần bật/tắt tập hook bằng thay đổi bytecode động ở runtime.
- Cần độ phủ rộng ở các loại join point mà **công cụ compile-time đang xét thực sự hỗ trợ**.

**Phản ví dụ:** một nhóm vận hành chỉ có quyền cấu hình production, không có quyền build lại artifact. Dù compile-time weaving có nhiều ưu điểm, nó có thể không đáp ứng yêu cầu triển khai thực tế.

## 5. Dệt binary/post-compile trước triển khai

### 5.1. Vị trí trong pipeline

```text
Source --compile--> bytecode gốc
                        |
                        v
                  binary weaver
                        |
                        v
                bytecode đã dệt
                        |
                        v
                 package/deploy
```

Lúc này hệ thống đã có binary nhưng chưa chạy. Một công cụ có thể sửa class file, assembly hoặc artifact phù hợp theo điều kiện được hỗ trợ.

### 5.2. Khi mô hình này có lợi

- Cần tách trách nhiệm giữa nhóm compile code nghiệp vụ và bước instrumentation.
- Có nhiều ngôn ngữ nguồn tạo cùng định dạng trung gian/bytecode mà weaver tương thích.
- Muốn inspect và kiểm chứng **artifact cuối** trước khi runtime.
- Muốn tạo các biến thể artifact được dệt và không được dệt phục vụ rollout hoặc thử nghiệm hiệu năng.

### 5.3. Điều kiện quan trọng

- Có quyền **biến đổi và phân phối** artifact liên quan; phải xét licensing, chữ ký binary và chính sách chuỗi cung ứng phần mềm.
- Phải có cách phân biệt artifact **chưa dệt / đã dệt** để tránh weave lặp gây hook trùng hoặc binary lỗi.
- Nếu một thư viện đã được ký, bước biến đổi có thể làm chữ ký cũ không còn hợp lệ; quy trình packaging/signing phải tính tới.
- Mapping source line và stack trace sau weaving có thể thay đổi; cần kiểm thử debug/diagnostic.
- Kết quả dùng đúng compiler/weaver/runtime tương thích, không chỉ “classfile hợp lệ ở một máy”.

### 5.4. Post-compile không đồng nghĩa load-time

Hai mô hình có thể cùng biến đổi bytecode, nhưng **thời điểm và trạng thái class khác nhau**: post-compile biến đổi file trước khi chạy; load-time can thiệp lúc class sắp được định nghĩa bởi loader. Điều này tác động đến kiểm thử, khả năng đảo chiều, ownership và độ phủ đối với những class được tạo/nạp riêng.

## 6. Load-time weaving: kết hợp khi class được nạp

### 6.1. Cơ chế tổng quát

Một class transformer/classloader hoặc hook tương tự xử lý class trước khi nó được định nghĩa trong runtime.

```text
Runtime cần load class
         |
         v
Classloader / transformer pipeline
         |
         +-- class ngoài include --> không biến đổi
         |
         +-- class hợp lệ -------> xét pointcut / weave
                                       |
                                       v
                              Runtime định nghĩa class
                                       |
                                       v
                              Các invocation tương lai
```

Một class đã load trước khi công cụ được cài có thể **không được xử lý bởi load-time hook đó**, trừ khi có cơ chế riêng dành cho class đã load. Vì vậy thời điểm **attach agent/đăng ký transformer** và việc runtime có nhiều loader rất quan trọng.

### 6.2. Lợi ích

- Có thể không cần phân phối binary đã biến đổi trước nếu runtime nhận transform ở lúc load.
- Có thể áp dụng scope dựa trên classloader/module/metadata runtime mà build pipeline không biết hết.
- Có thể phù hợp ứng dụng có **module/plugin được nạp động** nếu weaver được cấu hình và có quyền quan sát đúng loader.
- Dễ điều chỉnh phần nào phạm vi cho các class **chưa load**, theo cách công cụ hỗ trợ.

### 6.3. Đánh đổi

- **Startup/classloading overhead:** transformer có thể tốn CPU, allocation, I/O hoặc làm tăng độ trễ load class.
- **Khả năng chẩn đoán:** phải phân biệt “class loader đã thử xử lý”, “class thực sự được biến đổi” và “pointcut có hook”.
- **Classloader isolation:** một loader ngoài phạm vi có thể bỏ qua instrument.
- **Thứ tự agent/transformer:** nhiều công cụ có thể cùng động vào bytecode.
- **Quyền runtime:** môi trường có thể cấm attach/transformer hoặc module access.
- **Rollback:** thay config có thể không xóa hook khỏi class đã nạp.

### 6.4. Không mặc định “load-time là dynamic hot-swap”

Một class thường được định nghĩa một lần trong một classloader; “load-time weaving” không tự có nghĩa có thể thay đổi mọi method đang chạy bất cứ lúc nào. Cần phân biệt **class chưa load sẽ dùng policy mới** với **class đã load đã có hình thái runtime riêng**.

### 6.5. Khi phù hợp

Xem xét khi:

- Không muốn hoặc không thể build một artifact weaving trước.
- Có quyền khởi tạo/configure loader hoặc JVM agent **trước khi các class mục tiêu được load**.
- Cần instrumentation cho code nạp động theo quy tắc đã biết.
- Chấp nhận chi phí startup và có đủ test trên cấu trúc loader/module thực.

## 7. Runtime instrumentation và class retransformation

### 7.1. Tại sao đây là một lớp khác load-time?

Có công cụ có thể đính vào một process đang chạy và yêu cầu runtime biến đổi hoặc định nghĩa lại **một số class đã load**. Trên JVM, các API instrumentation có khái niệm **retransform/redefine**; khả năng thật sự phải được runtime và agent công bố.

Không nên suy rằng có thể thêm/bớt mọi loại field, đổi class hierarchy, thay signature hoặc sửa mọi bytecode tùy ý trên class đã chạy. Có những giới hạn về **kiểu thay đổi**, class modifiability, quyền truy cập và trạng thái class.

### 7.2. Khi cần thiết

- Chẩn đoán một hệ thống đang chạy mà việc redeploy tốn kém, nếu chính sách cho phép attach/instrument.
- Bật một loại profiling/trace tạm thời để tìm bottleneck.
- Cần thay đổi phạm vi đo ở runtime mà không muốn rebuild toàn bộ artifact, trong phạm vi engine hỗ trợ.

### 7.3. Rủi ro vận hành

- Cần **quyền attach agent** và quy trình phê duyệt bảo mật.
- Có thể cần dừng ngắn hoặc đồng bộ hóa tại safepoint khi retransform; chi phí phụ thuộc runtime.
- Hai agent cùng instrument một class có thể tạo xung đột.
- Một lần biến đổi sai có thể ảnh hưởng process đang phục vụ traffic.
- Việc “tắt agent” không bảo đảm bytecode đã bị biến đổi được khôi phục đúng, trừ khi công cụ có cơ chế undo/retransform đáng tin.
- Thay đổi class đang hoạt động có thể làm diagnostic và phiên bản hook khó truy vết.

Vì vậy runtime modification cần **canary, rollback, observability, audit trail và thử nghiệm cùng runtime phiên bản thật**.

### 7.4. Một mục tiêu “bật/tắt logging” không nhất thiết cần retransform

Nếu hook đã có sẵn, bật/tắt việc ghi log bằng config runtime có thể đủ mà không sửa class. Nhưng một hook đã cài vẫn có thể có overhead tối thiểu và điều kiện pointcut/runtime guard; phải đo.

Nên phân biệt:

- **Cài hoặc gỡ điểm can thiệp** (structural change).
- **Bật/tắt hành vi của advice đã cài** (behavior/config change).
- **Lọc những event được ghi/hiển thị** (observability pipeline).

Ba việc này có tác động khác nhau đến correctness và performance.

## 8. Runtime proxy/decorator: không nhất thiết dệt bytecode

### 8.1. Dynamic proxy

Một proxy theo interface có thể nhận lời gọi từ caller, chạy handler rồi gọi target. Việc tạo proxy có thể xảy ra lúc runtime, nhưng target class **không tự bị biến đổi**.

```text
Caller --> Proxy --> Handler/advice --> Target
Caller -------------------------------> Target   (bypass)
```

Ưu điểm:
- Có thể lắp ghép/tắt tại ranh giới tạo object.
- Không nhất thiết cần thay đổi source/bytecode target.
- Dễ kiểm thử từng wrapper và dependency injection theo hợp đồng.

Giới hạn:
- Caller có thể giữ target gốc và bỏ qua proxy.
- Self-invocation trên `this` có thể không đi qua proxy.
- JDK dynamic proxy theo interface không tự chặn constructor/field access.
- Đối tượng, kiểu, identity và reflection của proxy có thể khác target.

### 8.2. Explicit decorator

Một decorator viết bằng Java thuần là wrapper triển khai cùng interface và gọi target. Nó có thể được **viết lúc development nhưng lắp ghép lúc build startup hoặc runtime**; không được gọi đó là “compile-time bytecode weaving” chỉ vì class decorator đã được compile.

Decorator có lợi khi cần nhìn thấy luồng rõ ràng và không cần join-point model phức tạp. Proxy có thể phù hợp khi nhiều interface methods cần handler thống nhất. Cả hai có thể dùng để minh họa sự lựa chọn **interception mechanism** nhưng không thay thế thảo luận về weaving thật.

### 8.3. Khi nào proxy đáp ứng yêu cầu?

Nếu hệ thống chỉ cần chặn **lời gọi công khai qua một interface boundary đã kiểm soát**, proxy/decorator có thể là lựa chọn đơn giản.

Nếu cần can thiệp **field access, constructors, private methods** hoặc những lời gọi nội bộ không đi qua boundary, cần công cụ có join-point model và cơ chế phù hợp; không thể biến proxy thành công cụ toàn năng bằng một pattern include rộng.

## 9. Ma trận yêu cầu để chọn thời điểm

Bảng dưới là **khung quyết định định tính**, không phải số liệu benchmark hoặc cam kết về từng sản phẩm.

| Yêu cầu | Hướng thường đáng xem xét | Phải xác minh |
| --- | --- | --- |
| Artifact phải được ký, review và tái lập trước deploy. | Compile-time hoặc post-compile weave có kiểm soát. | Artifact cuối đã được weave và ký đúng thứ tự. |
| Không cho phép runtime agent/attach. | Build/binary weaving hoặc wrapper đã đóng gói. | Runtime không cần quyền transform. |
| Chỉ có binary và không kiểm soát pipeline build. | Load-time/runtime instrumentation nếu được phép; hoặc proxy ở boundary khả dụng. | Licensing, agent privileges, classloader và tương thích. |
| Nhiều plugin/classloader được nạp sau startup. | Load-time weaving theo loader; wrapper ở plugin boundary. | Transformer thấy đúng loader và class. |
| Cần thay đổi instrumentation trong process đang chạy. | Runtime config trên hook sẵn có; retransformation khi cần và khả dụng. | Giới hạn modifiable class, rollback, phí tổn. |
| Startup latency rất nhạy. | Dệt trước chạy hoặc proxy nhẹ đã đo kiểm. | Cost chuyển từ startup sang build/run thế nào? |
| Cần can thiệp private/constructor/field. | Engine có mô hình join point rộng với compile/load-time weaving phù hợp. | Cú pháp, visibility, class constraints. |
| Chỉ cần ghi log ở interface service boundary. | Decorator/dynamic proxy hoặc weaving có scope hẹp. | Mọi caller có thật qua wrapper không? |
| Chính sách bảo mật không được bypass. | Bảo vệ ở trusted boundary/domain invariant, weaving chỉ hỗ trợ. | Không có đường truy cập bỏ qua bất biến. |
| Muốn overhead có thể dự đoán và benchmark. | Mô hình nào cũng có thể phù hợp nếu đo đầy đủ. | Runtime occurrences, dynamic guards, logging cost. |
| Cần canary/rollback trong production. | Artifact-based rollout hoặc instrumentation có cơ chế undo đã kiểm chứng. | Không nhầm “tắt config” với unweave class. |
| Có native/AOT/deployment đóng. | Cơ chế được toolchain AOT hỗ trợ; thường cần tích hợp build sớm. | Reflection/proxy/agent availability và closed-world constraints. |

Chọn thời điểm là **bài toán nhiều tiêu chí**. “Nhạy hiệu năng” không tự chỉ ra compile-time weaving; nếu advice ghi log mạng ở một hot path, bất cứ thời điểm weave nào cũng có thể gây chi phí lớn.

## 10. Quy trình quyết định tám bước

### Bước 1 — Nêu concern và hợp đồng hành vi

Muốn đo thời gian, audit, retry, quản lý transaction hay kiểm soát quyền? Advice chỉ quan sát hay có thể đổi result/exception? Có bắt buộc không thể bị bypass?

Nếu hành vi ảnh hưởng an toàn dữ liệu hoặc quyền truy cập, phải bảo vệ bằng **domain/trusted boundary** phù hợp trước; weaving có thể hỗ trợ nhưng không phải chứng cứ duy nhất rằng mọi đường đã được chặn.

### Bước 2 — Chọn join-point model cần thiết

Ghi rõ:
- Method call hay execution?
- Constructor, field get/set hoặc event đặc thù?
- Có cần biết caller, receiver runtime, arguments hay annotation?
- Có cần bao quanh async **task completion**, chứ không chỉ method return?

Nếu chỉ có proxy nhưng yêu cầu private field writes, kế hoạch không khả thi; cần thay đổi công cụ hoặc ranh giới kiến trúc.

### Bước 3 — Xác định ai sở hữu code/artifact

Hệ thống có:
- Source code và quyền build?
- Binary third-party nhưng không có source?
- Module được tải từ bên ngoài sau deploy?
- Artifact được ký hoặc yêu cầu supply-chain attestation?
- Quy định không sửa binary của dependency?

Một công cụ weaving có thể về mặt kỹ thuật làm được nhưng bị chính sách phân phối hoặc quyền truy cập cấm.

### Bước 4 — Xác định thời điểm được phép thay đổi

Nếu policy phải cố định theo release → dệt trước runtime thuận lợi cho QA. Nếu cần bật instrumentation trên một process đang chạy → xét runtime configuration/retransformation. Nếu class nạp động và agent có sẵn từ startup → load-time có thể phù hợp. Nếu chỉ cần đổi một wrapper ở module boundary → proxy/decorator có thể đủ.

### Bước 5 — Xác định startup, throughput và footprint

Đo các chi phí riêng:
- **Build time** thêm vì weaving.
- **Startup/classload time** thêm vì transformer.
- **Memory/metadata footprint** của hook, proxy, cache.
- **Steady-state overhead** khi join point xảy ra.
- **Cost của advice**: log I/O, serialize, metrics cardinality, lock.
- **Chi phí đổi cấu hình/rollout**.

Không gộp tất cả thành một con số “AOP overhead”.

### Bước 6 — Chọn chính sách include/exclude

Ưu tiên danh sách được phép có chủ đích, xác định class/module/package/loader được xét và loại trừ code instrumentation tránh recursion. Cần phân biệt **weaving eligibility** với **pointcut exclusion**: exclude cả class khỏi weaving có thể khiến nhiều aspect mất hook; exclude một pointcut có tác động hẹp hơn.

Ghi rõ precedence nếu một class khớp cả include và exclude. Không giả định deny luôn thắng ở mọi công cụ; phải xác minh hợp đồng.

### Bước 7 — Xây thử nghiệm đúng cùng runtime

Không chỉ test biểu thức pointcut. Phải test:
- Artifact/build output đã thực sự weave?
- Classloader nào được transformer nhìn thấy?
- Pointcut khớp join point nào?
- Positive/negative runtime occurrences có advice đúng?
- Trường hợp bypass proxy, self-call, async completion?
- Errors/advice order/context/thread safety?
- Hiệu năng dưới tải thực?

### Bước 8 — Có kế hoạch vận hành và quay lại

Với build weaving: rollback artifact/version. Với load-time: quay config và restart/rollout nếu class đã load không thể unweave. Với runtime retransformation: xác nhận undo thật và hành vi khi agent bị lỗi. Với proxy: thay đổi wiring/reference theo policy, bảo đảm caller không giữ target gốc trái ý định.

## 11. Ba tình huống chọn chiến lược chi tiết

### Tình huống A — Ứng dụng xử lý giao dịch có release nghiêm ngặt

**Yêu cầu:**
- Code ứng dụng do team sở hữu.
- Mọi artifact cần CI/test/scan/sign trước production.
- Không cho phép attach agent động.
- Cần log các method execution tại một số tầng ổn định.

**Hướng quyết định:** cân nhắc compile-time hoặc post-compile weaving nếu engine hỗ trợ join point, hoặc một interceptor/decorator cố định tại boundary khi đủ. Điểm quan trọng là **artifact cuối cùng chứa đúng hook và được QA trước khi ký/phân phối**.

**Không suy ra:** build weaving tự đảm bảo mọi policy bảo mật đã bao phủ; vẫn phải kiểm thử bypass, lỗi và transaction semantics.

### Tình huống B — Nền tảng plugin nạp class động

**Yêu cầu:**
- Plugin được nạp sau startup và có classloader riêng.
- Không thể rebuild tất cả plugin khi host nâng cấp.
- Cần đo latency ở những class/plugin đã được phép.

**Hướng quyết định:** load-time weaving có thể phù hợp nếu transformer được đăng ký trước plugin load và có quyền quan sát loader/plugin. Một decorator quanh **plugin API boundary** cũng có thể tốt hơn nếu chỉ cần đo lời gọi từ host.

**Rủi ro cần kiểm tra:** tên class pattern đúng nhưng plugin dùng loader không qua transformer; version mismatch; unload plugin mà cache metadata/agent giữ classloader; plugin gọi nội bộ không qua API boundary.

### Tình huống C — Điều tra sự cố production ngắn hạn

**Yêu cầu:**
- Hệ thống đã chạy, khó tái triển khai tức thì.
- Cần thu thêm trace cho một số class trong khoảng thời gian giới hạn.
- Hệ thống có chính sách cho phép công cụ chẩn đoán được cấp quyền.

**Hướng quyết định:** dùng hook đã cài sẵn và bật runtime config nếu có. Nếu chưa có hook, runtime instrumentation/retransformation có thể là lựa chọn **chỉ khi** runtime/agent hỗ trợ và có canary + rollback.

**Rủi ro:** làm biến đổi class nhạy cảm khi đang phục vụ request; overhead làm sự cố tệ hơn; log lộ dữ liệu; không có cách unweave ổn định. Nên có TTL cho cấu hình chẩn đoán, sampling và kiểm soát truy cập.

## 12. Java 17 runnable: ranh giới khi lắp decorator và tạo dynamic proxy

Java chuẩn không có một API “dệt mọi join point” tổng quát. Để thấy khác biệt giữa **lắp một wrapper tường minh** và **tạo một proxy khi chạy**, ta dùng interface, target, decorator và JDK dynamic proxy.

**Quan trọng:** Chương trình dưới **không triển khai compile-time weaving, post-compile binary weaving, load-time transformer hay retransformation**. Nó chỉ minh họa hai mô hình interception dựa trên **object reference**. Dựa vào demo này không được kết luận bất kỳ bytecode nào đã bị dệt.

Tạo file **`WeavingTimingDecisionDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class WeavingTimingDecisionDemo {
    interface Work {
        String run(String value);
    }

    static final class RealWork implements Work {
        @Override
        public String run(String value) {
            System.out.println("TARGET " + value);
            if ("FAIL".equals(value)) {
                throw new IllegalStateException("operation failed");
            }
            return "OK:" + value;
        }
    }

    static Work decorate(Work target) {
        return new Work() {
            @Override
            public String run(String value) {
                System.out.println("DECORATOR before");
                try {
                    String result = target.run(value);
                    System.out.println("DECORATOR returning");
                    return result;
                } catch (RuntimeException ex) {
                    System.out.println("DECORATOR throwing "
                            + ex.getClass().getSimpleName());
                    throw ex;
                }
            }
        };
    }

    static Work proxy(Work target) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] { Work.class },
                (proxyInstance, method, args) -> {
                    System.out.println("PROXY before");
                    try {
                        Object result = method.invoke(target, args);
                        System.out.println("PROXY returning");
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        System.out.println("PROXY throwing "
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                }
        );
    }

    public static void main(String[] args) {
        Work target = new RealWork();

        System.out.println("RESULT " + target.run("A"));

        Work decorator = decorate(target);
        System.out.println("RESULT " + decorator.run("B"));

        Work runtimeProxy = proxy(target);
        System.out.println("RESULT " + runtimeProxy.run("C"));

        try {
            runtimeProxy.run("FAIL");
        } catch (IllegalStateException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        System.out.println("RESULT " + target.run("DIRECT"));
    }
}
```

Biên dịch và chạy:

```bash
javac WeavingTimingDecisionDemo.java
java WeavingTimingDecisionDemo
```

Stdout theo đúng thứ tự:

```text
TARGET A
RESULT OK:A
DECORATOR before
TARGET B
DECORATOR returning
RESULT OK:B
PROXY before
TARGET C
PROXY returning
RESULT OK:C
PROXY before
TARGET FAIL
PROXY throwing IllegalStateException
CALLER caught operation failed
TARGET DIRECT
RESULT OK:DIRECT
```

### 12.1. Direct target — không có interception

`target.run("A")` và `target.run("DIRECT")` đi thẳng vào `RealWork`, vì thế chỉ có dòng TARGET/RESULT. Việc target có thể được bọc bằng decorator hay proxy ở chỗ khác không thay đổi call path của reference gốc.

Đây là điều quan trọng khi cân nhắc proxy: **khả năng tạo wrapper khác với khả năng buộc mọi caller dùng wrapper**.

### 12.2. Decorator — lắp ghép được kiểm soát

`decorate(target)` tạo một object khác thực hiện `Work`. Code của decorator được viết tường minh, nhưng việc nó được lắp vào ứng dụng diễn ra khi chạy. Lời gọi `decorator.run("B")` in before, target, returning rồi kết quả.

Không gọi hình thức này là “compiler đã weave body của `RealWork`”. Nó là composition/wrapping đã được lập trình viên tạo ra.

### 12.3. Dynamic proxy — handler tạo khi chạy

`Proxy.newProxyInstance` sinh một object proxy triển khai `Work`; handler nhận invocation qua proxy. Handler dùng reflection để gọi target, ghi trước/sau và gỡ `InvocationTargetException` khi target ném lỗi.

Với `runtimeProxy.run("FAIL")`, target in `TARGET FAIL` rồi ném `IllegalStateException`; handler in `PROXY throwing IllegalStateException`, chuyển tiếp nguyên nhân để caller nhận `operation failed`.

**Chú ý:** Code chỉ minh họa một method được caller gọi. Với một interface có các method kế thừa từ `Object`, overload hoặc default methods, handler thực tế cần cách xử lý chính xác những invocation đó theo hợp đồng; không dựa vào demo đơn giản để khẳng định proxy bao mọi trường hợp.

### 12.4. Kết luận từ demo — và giới hạn của kết luận

Bạn có thể chứng minh:
- Decorator/proxy có thể tạo một boundary kiểm soát lời gọi.
- Advice trong wrapper chạy **khi caller dùng wrapper**.
- Direct call vào target không đi qua wrapper.
- Có thể giữ nguyên kết quả/exception bằng cách tiếp tục gọi target đúng cách.

Bạn **không thể** chứng minh:
- Một class đã được compile-time/load-time weave.
- Constructor, field hoặc private method đã có hook.
- Công cụ AOP cụ thể hỗ trợ retransform class đã load.
- Bản thân việc tạo proxy làm thay đổi bytecode của target.
- Mọi caller của target đã được bao phủ.

Để kiểm chứng những điều đó, cần một công cụ weaving tương ứng và inspection/runtime tests cho chính artifact được chọn.

## 13. Chọn theo loại join point thay vì chỉ tên thời điểm

### 13.1. Method execution và method call

Một công cụ có thể phân biệt join point ở **phía method body bắt đầu thực thi** và join point ở **vị trí gọi method**. Một method có thể được gọi từ nhiều call site; một call site trong loop có thể chạy nhiều lần.

Nếu yêu cầu đo mọi execution của một method, một hook ở implementation có thể phù hợp hơn hook ở một vài call site cụ thể. Nếu yêu cầu theo dõi caller cụ thể, method-call join point có thể cần thiết. Phải kiểm tra công cụ ở thời điểm weaving nào hỗ trợ từng loại điểm; không mặc định mọi kỹ thuật có cùng tập điểm.

### 13.2. Field access và constructor

JDK interface proxy không tự chặn việc đọc/ghi field hoặc tạo object trước khi có proxy. Một số công cụ weaving tại source/bytecode có thể hỗ trợ những điểm đó, nhưng cần xem giới hạn về visibility, class verification và định nghĩa join-point model.

Đây là ví dụ **loại điểm quan trọng hơn nhãn “compile/load/runtime”**. Chọn sai công cụ dù đúng thời điểm cũng không đáp ứng yêu cầu.

### 13.3. Self-invocation và recursion

Nếu target gọi một method khác trên `this`, đường đó thường **không đi lại qua JDK proxy**. Với một engine weave trực tiếp vào body, kết quả có thể khác. Nếu yêu cầu đo mọi execution kể cả gọi nội bộ/đệ quy, cần kiểm tra bằng test thực chứ không suy từ chữ “AOP”.

### 13.4. Async completion

Một around advice bao quanh method trả `CompletionStage` thường kết thúc khi method **trả handle**, không tự kéo dài tới lúc task hoàn thành. Nếu phải đo end-to-end latency, cần hook theo completion API hoặc join point khác mà công cụ hỗ trợ. Thời điểm cài hook vào class **không tự giải quyết lifecycle bất đồng bộ**.

## 14. Hạn chế và tương thích công nghệ

### 14.1. Bytecode version và verifier

Một transformer phải tạo output tương thích class file format và runtime verifier. Sau khi nâng compiler/JDK, một engine chưa hỗ trợ bytecode mới có thể lỗi khi load hoặc tạo instrumentation sai. Cần pin/test ma trận compiler, JDK, weaver và dependency thực.

### 14.2. Debug symbols và stack trace

Source-time/post-compile/load-time weaving có thể thay đổi số lượng instruction, frame, method phụ hoặc call stack. Công cụ có thể bảo toàn mapping tốt, nhưng không được hứa line numbers/stack traces giống trước khi weave trong mọi trường hợp. Cần kiểm thử logging, exception và profiling.

### 14.3. Reflection, module và security boundary

Một số agent/proxy dùng reflection hoặc cần module access. Quyền truy cập tại runtime có thể bị giới hạn. Cấu hình include một class không đủ để vượt quy định của module system hoặc policy bảo mật. Không nên mở rộng quyền runtime quá mức cần thiết chỉ để “cho weaving chạy”.

### 14.4. Native image hoặc AOT

Trong môi trường closed-world/AOT, nhiều khả năng runtime bytecode generation, reflection hoặc attach có thể không khả dụng giống một JVM động. Nếu hệ thống cần AOT/native, phải đánh giá toolchain từ sớm; một lựa chọn build-time có thể phù hợp, nhưng vẫn tùy framework, compiler, reflection configuration và cơ chế weaving được hỗ trợ.

### 14.5. Dynamic code generation

Khi ứng dụng sinh class ở runtime, class đó có thể không tồn tại trong artifact build. Build-time weaving sẽ không tự xử lý mã chưa được tạo, trừ khi architecture đã biết cách instrument output trước hoặc trong quá trình sinh. Load-time transformer có thể thấy class sinh ra trong một số mô hình, nhưng cần đúng loader/hook; không có bảo đảm chung.

## 15. Kiểm soát phạm vi, nhiều agent và khả năng trùng hook

### 15.1. Include/exclude ở đúng tầng

Một chính sách có thể gồm:
- **Eligible classes/artifacts**: lớp nào được phép biến đổi.
- **Join-point kind**: loại sự kiện nào engine hỗ trợ.
- **Pointcut matcher**: method/annotation/arguments nào khớp.
- **Runtime condition**: lượt xảy ra nào thỏa điều kiện động.

Exclude toàn bộ class khỏi weaving có thể tắt nhiều aspect trên class đó, trong khi điều kiện `NOT internal` ở một pointcut có thể chỉ tắt một advice. Cần xem hậu quả lên tracing, metrics, audit và logic kỹ thuật khác.

### 15.2. Hai weaver cùng chạm một class

Nếu pipeline có nhiều compiler transform, binary weaver hoặc runtime agent, chúng có thể áp dụng trên output của nhau. Thứ tự biến đổi, tính idempotent và khả năng tương thích rất quan trọng.

Tình huống thường phải kiểm:
- Artifact đã được weave ở build nhưng runtime agent cũng instrument cùng method.
- Một agent retransform class nhiều lần và thêm hook trùng.
- Một transformer giả định cấu trúc bytecode gốc trong khi transformer trước đã đổi nó.
- Pointcut rộng chọn cả code instrumentation gây vòng lặp `advice -> logger -> advice`.

Cần có rule tránh biến đổi mã của chính logging/metrics/advice runtime khi không có chủ đích, đồng thời kiểm thử những chính sách khác không bị vô tình loại.

### 15.3. Không xem mọi duplicate log là “weaving kép”

Hai advice riêng có thể cùng chọn một join point một cách hợp lệ. Một logical operation cũng có thể đi qua method call và execution join points, hoặc retry nhiều lần. Phải phân biệt **trùng hook ngoài ý định** với **nhiều sự kiện/advice có chủ đích** bằng correlation, attempt ID và thông tin về điểm can thiệp.

## 16. Đánh giá hiệu năng bằng số đo đúng loại

Một phương án có thể tăng **build time** nhưng giảm **startup transform time**. Một phương án khác có thể không làm chậm build nhưng tăng **classloading latency**. Proxy có thể thêm dispatch/reflection cost ở mỗi invocation. Những con số này khác nhau, không thể gọi chung là “chậm hơn”.

### 16.1. Những metric nên thu

| Thời điểm | Metric có giá trị |
| --- | --- |
| Compile/build weaving | Thời gian compile/transform, kích thước artifact, số class được xử lý, cache misses. |
| Post-compile binary weaving | Số bytecode artifacts thay đổi, thời gian patch, ký/verify, số lỗi class verification. |
| Load-time weaving | Startup time, time spent transforming, số class load/transform, số lỗi loader. |
| Runtime retransformation | Thời gian retransform, số class affected, mức gián đoạn, lỗi, thời gian rollback. |
| Runtime proxy/decorator | Chi phí dispatch theo invocation, allocation, khả năng inline/optimize, call-path coverage. |
| Mọi chiến lược | Advice invocation rate, CPU/memory, tail latency, I/O telemetry, GC, throughput. |

Một class eligible nhưng method ít được gọi có thể tạo overhead runtime rất thấp; một method hot path được gọi hàng triệu lần có thể tốn kém dù chỉ có một class được weave. Phải đo theo **runtime occurrences** và payload thực.

### 16.2. Benchmark phải tách overhead của cơ chế khỏi overhead của advice

Một phép đo có thể so sánh:
1. Không instrument.
2. Có hook nhưng advice rỗng/không ghi I/O.
3. Có advice thực nhưng dùng sink giả có kiểm soát.
4. Có logging/tracing production với sampling, queue và backend.

Nếu chỉ so AOP có log mạng với code không log, chênh lệch không chứng minh do **thời điểm weaving**. Đo p50/p95/p99 trong workload đại diện, kể cả startup/redeploy nếu đó là yêu cầu.

### 16.3. Yêu cầu ổn định cũng bao gồm failure mode

Một transformer lỗi lúc load có thể làm class không định nghĩa được, kéo sập startup. Một proxy handler lỗi có thể làm invocation thất bại. Một aspect ném exception trong cleanup có thể che lỗi target. Vì vậy đánh giá performance phải đi cùng **resilience/correctness**, không chỉ microbenchmark.

## 17. CI/CD, artifact provenance và rollback

### 17.1. Với weaving trước runtime

Pipeline gợi ý:

```text
Compile
  -> Weave / transform
  -> Inspect / verify output
  -> Unit + integration tests
  -> Performance / compatibility checks
  -> Package + sign
  -> Deploy canary
  -> Promote / rollback artifact
```

Đảm bảo **artifact được ký là artifact sẽ chạy**, không ký binary trước rồi weave sau khiến chữ ký không còn phản ánh bytes thực. Nếu hệ thống có SBOM và provenance, bước biến đổi phải được mô tả như một phần của build pipeline.

### 17.2. Với load-time weaving

Pipeline vẫn cần kiểm thử với **cùng flags/agent order, classloader graph và quyền module** như production. Không đủ nếu unit tests chỉ chạy code mà chưa bật transformer.

Rollout có thể cần restart để những class đã load nhận phiên bản weave mới. Không khẳng định restart luôn cần cho mọi engine; kiểm tra khả năng unweave/retransform của công cụ.

### 17.3. Với runtime instrumentation

Phải có:
- Danh tính và quyền người/tiến trình được phép attach.
- Danh sách class/pointcut nằm trong scope.
- Canaries và ngưỡng dừng khi CPU/latency/error rate tăng.
- Biện pháp không ghi dữ liệu nhạy cảm.
- TTL cho cấu hình chẩn đoán.
- Kiểm chứng cơ chế rollback/untransform thực tế.
- Audit sự kiện thay đổi instrumentation.

Một “toggle OFF” có thể chỉ khiến advice không ghi log, trong khi bytecode vẫn bị biến đổi. Báo cáo rollout phải diễn đạt đúng điều đã thay đổi.

## 18. Kiểm thử chứng minh lựa chọn thời điểm đáp ứng yêu cầu

### 18.1. Unit test cho bộ chọn policy

Cho danh sách class/module đại diện:

| Class/kiểu | Kỳ vọng |
| --- | --- |
| `app.orders.OrderService` | Được xét nếu nằm trong allowlist. |
| `app.internal.Metrics` | Có thể loại khỏi pointcut/logging tránh recursion. |
| `vendor.adapter.Client` | Theo policy có/không instrument dependencies. |
| `app.generated.Mapper` | Phụ thuộc chiến lược generated-code rõ ràng. |
| Class nested/bridge/synthetic | Theo tên binary/metadata thực, không đoán từ source. |

Nếu engine có include/exclude ở cấp classloader/module, bổ sung test đúng ranh giới ấy.

### 18.2. Build-time evidence

Với compile/post-compile weaving, kiểm tra binary thực:
- Hook hoặc biến đổi có nằm trong artifact cuối không?
- Tên method/descriptor còn đúng không?
- Bytecode có verify trên runtime mục tiêu không?
- Pointcut match đúng và không sinh duplicate advice?
- Debug/exception behavior có đúng không?

Đừng chỉ tin build thành công: bước weaving có thể bị skip vì config, incremental cache hoặc artifact khác được deploy.

### 18.3. Load-time evidence

Với load-time:
- Transformer được đăng ký **trước** thời điểm class mục tiêu load chưa?
- Class nào được **xét** và class nào **thực sự transform**?
- Classloader và module nào xử lý?
- Có lỗi module access/verification không?
- Những class có cùng tên nhưng khác loader có được xử lý đúng không?

### 18.4. Runtime evidence

Bất kể cơ chế:
- **Positive:** join point đủ điều kiện, pointcut khớp, runtime xảy ra → advice đúng.
- **Negative scope:** class nằm ngoài eligible không bị can thiệp ngoài ý định.
- **Negative pointcut:** method không khớp không nhận advice đó.
- **Bypass:** đường gọi trực tiếp vào target trong mô hình proxy được xác định rõ.
- **Nested/self-call:** quan sát thực tế thay vì suy luận.
- **Error path:** exception type/cause được bảo toàn theo hợp đồng.
- **Async:** return handle vs task completion được phân loại đúng.
- **Concurrency:** không rò context hoặc trộn state của các invocation.
- **Performance:** chi phí phù hợp ngân sách tại workload thật.

### 18.5. Test nâng cấp và rollback

Khi thay compiler/runtime/weaver:
1. Rebuild với version mới.
2. So artifact transformed và class counts.
3. Chạy integration tests cho cả target và advice.
4. So performance và startup.
5. Deploy canary, theo dõi error/latency.
6. Thử rollback đúng thủ tục khi có vấn đề.

Một chiến lược “có thể lắp trong runtime” nhưng **không có rollback an toàn** có thể kém phù hợp production hơn một artifact-based release dù việc cập nhật mất thêm thời gian.

## 19. Sai lầm thường gặp khi chọn thời điểm weaving

**“Compile-time weaving nghĩa là advice chạy khi biên dịch.”** Sai. Advice thường chạy khi runtime đến join point; compile-time là thời điểm cài logic.

**“Load-time weaving có thể sửa mọi class bất kỳ lúc nào.”** Sai. Class đã load cần cơ chế khác và có giới hạn riêng.

**“Đã có Java agent thì retransform được mọi thay đổi cấu trúc class.”** Sai. Phải xem runtime capabilities, class modifiability và giới hạn loại thay đổi.

**“Runtime proxy tức là bytecode của target đã được weave.”** Sai. Proxy có thể là object riêng; target ban đầu không bị sửa.

**“Chọn compile-time là hiệu năng runtime luôn tối ưu.”** Không có bảo đảm. Advice vẫn tạo chi phí và công cụ có trade-off riêng.

**“Chọn load-time là không cần kiểm thử artifact.”** Sai. Binary gốc, transformer, cấu hình, classloader và runtime kết hợp mới tạo hành vi cuối.

**“Pointcut match nên mọi caller sẽ chạy advice.”** Sai nếu caller bỏ qua proxy, join point không xảy ra hoặc class không được weave.

**“Hot reload config tức là unweave code đã cài.”** Không thể mặc định. Cần cơ chế undo/retransform được chứng minh.

**“Dệt trước runtime luôn bao được generated code.”** Chưa chắc mã ấy được sinh sau thời điểm dệt hoặc nằm ngoài build graph.

**“Mọi app có cùng yêu cầu do đều dùng Java 17.”** Sai. Classloader, module, đóng gói, lifecycle, JIT, native image và chính sách vận hành khác nhau.

**“Một benchmark nhỏ đủ chọn chiến lược.”** Không. Phải tính build/startup/run overhead, failure modes, đổi chính sách, rollback và đúng join-point model.

**“Muốn bảo mật thì chỉ cần weave advice kiểm tra quyền.”** Không đủ khi có đường bypass hoặc biến đổi thiếu độ phủ. Authorization invariant cần được bảo đảm ở tầng tin cậy.

## 20. Bài tập quyết định

### Bài 1 — Runtime bị cấm attach agent

Ứng dụng có source và CI kiểm soát chặt. Chính sách yêu cầu mọi binary cuối phải có chữ ký; runtime không cho attach agent. Bạn chọn hướng nào?

**Đáp án gợi ý:** Xem xét compile-time/post-compile weaving hoặc wrapper đóng gói; nếu weave binary thì verify/test/sign **sau biến đổi**. Kiểm tra công cụ hỗ trợ join points cần thiết, không chọn chỉ vì tên kỹ thuật.

### Bài 2 — Chỉ có interface boundary

Ứng dụng chỉ cần ghi trace khi gọi `PaymentPort.charge()`, mọi caller được quản lý qua cùng factory. Có nhất thiết phải bytecode weave không?

**Đáp án:** Không nhất thiết. Decorator hoặc interface proxy có thể đủ nếu call path được bảo đảm và hợp đồng observability rõ; kiểm thử bypass/self-call.

### Bài 3 — Plugin load sau startup

Host tải plugin qua loader riêng. Một load-time transformer chỉ gắn cho app classloader. Pattern class trông đúng nhưng không thấy advice. Nguyên nhân khả dĩ?

**Đáp án:** Transformer không thấy plugin loader, hoặc plugin class đã load trước khi hook được cài, ngoài những khả năng khác như pointcut không khớp. Cần diagnostic classloader và thời điểm load.

### Bài 4 — Cần thay đổi logging ngay trong production

Nếu đã có hook nhưng có config runtime bật/tắt logging, có nhất thiết retransform class?

**Đáp án:** Không. Có thể chỉ đổi policy của advice/hook có sẵn; cần đo overhead còn lại và giới hạn dữ liệu, không nhầm với unweave.

### Bài 5 — Cần quan sát field writes

JDK interface proxy đang chạy tốt cho method calls. Có thể thêm `@Observed` vào field để proxy tự chặn setter bypass và direct field writes không?

**Đáp án:** Không. Annotation chỉ là metadata; proxy không tự có field-access join point. Cần công cụ hỗ trợ loại điểm và cơ chế thích hợp.

### Bài 6 — Đo end-to-end async

Một around advice dệt ở compile time quanh method trả `CompletableFuture`, đo tới khi `proceed()` trả handle. Có phải đã đo hết task?

**Đáp án:** Không. Thời điểm dệt không đổi sự khác biệt giữa method return và task completion. Phải quan sát terminal event của future/task.

### Bài 7 — Rollback

Bạn tắt agent sau khi instrument class đang chạy. Điều đó bảo đảm method trở lại bytecode gốc chưa?

**Đáp án:** Không mặc định. Cần xem agent có undo/retransformation hay cần restart/rollback artifact; có thể chỉ tắt handler nhưng bytecode đã biến đổi vẫn tồn tại.

### Bài 8 — Tối ưu hiệu năng

Load-time weaving làm startup chậm đáng kể nhưng runtime throughput tương đương. Phần lớn deployment là serverless short-lived tasks. Hướng đánh giá?

**Đáp án:** Startup/cold-start là yêu cầu trọng yếu; cân nhắc dệt trước runtime hoặc scope hẹp hơn, benchmark đúng workload và kiểm tra tính khả thi. Không khẳng định chiến lược mới chắc nhanh hơn khi chưa đo.

## 21. Checklist chọn và quản trị thời điểm weaving

1. **Mục tiêu:** Concern là gì, advice chỉ quan sát hay thay đổi hành vi?
2. **Join points:** Call, execution, constructor, field hay event đặc thù?
3. **Artifact ownership:** Có source, binary, quyền build/modify/sign/deploy không?
4. **Thời điểm:** Class được sinh/load khi nào, có đổi policy trong process không?
5. **Tool capability:** Compiler/weaver/agent hỗ trợ những điểm/kiểu bytecode nào?
6. **Runtime policy:** Có cho phép agent, retransform, reflection/module access không?
7. **Scope:** Những module/classloader/artifact nào đủ điều kiện, loại trừ ra sao?
8. **Compatibility:** Compiler/JDK/native image/module, generated classes và dependencies thế nào?
9. **Artifact evidence:** Có thể inspect transform output và verify bytes deploy không?
10. **Runtime evidence:** Positive/negative tests có chứng minh hook và occurrence thực không?
11. **Error semantics:** Exception, result, advice precedence và retry có được giữ đúng không?
12. **Async semantics:** Chỉ method invocation hay toàn bộ task completion?
13. **Performance:** Tách build/startup/retransform/invocation/advice I/O overhead chưa?
14. **Privacy/security:** Có tránh dữ liệu nhạy cảm và bypass policy quan trọng không?
15. **Operational change:** Cần hot config, canary, rollback và audit trail thế nào?
16. **Maintenance:** Refactor/package/module updates có làm scope silently thay đổi không?

## Kết luận

Không có thời điểm dệt AOP “tốt nhất cho mọi hệ thống”. **Compile/source-time** và **post-compile weaving** thuận lợi khi muốn kiểm soát, kiểm thử và phân phối artifact đã biến đổi trước runtime; **load-time weaving** phù hợp khi cần xử lý class lúc được nạp và quản lý loader; **runtime instrumentation** có thể mang lại linh hoạt trong giới hạn quyền và khả năng sửa class; **proxy/decorator** đơn giản hơn cho những boundary được kiểm soát nhưng không tự cung cấp mọi join point.

Hãy quyết định từ **yêu cầu join-point model, ownership artifact, khả năng vận hành, chi phí ở từng giai đoạn và bằng chứng QA**. Chọn đúng thời điểm chỉ là một phần: còn phải bảo đảm class nằm trong scope, pointcut khớp, hook đã cài và runtime thật sự đi qua nó. Một lựa chọn tốt là lựa chọn có thể **giải thích, kiểm thử, đo lường, triển khai và rollback** với rủi ro được kiểm soát.
