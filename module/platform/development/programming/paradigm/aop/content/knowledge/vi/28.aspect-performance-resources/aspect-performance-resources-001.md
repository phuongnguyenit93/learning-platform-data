# Chi phí khớp pointcut ở thời điểm dệt và thời điểm chạy trong AOP

## 1. Vấn đề cần hiểu

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **aspect** đóng gói một mối quan tâm xuyên suốt (ví dụ: đo thời gian, ghi vết, kiểm tra chính sách); **pointcut** mô tả tập các **join point** mà advice có thể áp dụng. Join point là một sự kiện/vị trí được mô hình AOP hỗ trợ, chẳng hạn lời gọi phương thức hoặc lúc phương thức bắt đầu thực thi. **Weaver** kết hợp aspect với chương trình tại thời điểm biên dịch, sau biên dịch, khi nạp lớp, hoặc theo một cơ chế tích hợp khác.

Câu hỏi hiệu năng quan trọng không đơn giản là “pointcut dài hay ngắn?”, mà gồm hai chi phí tách biệt:

- **Chi phí lúc dệt (weaving-time matching):** tìm những vị trí trong mã có thể được pointcut chọn, phân tích chữ ký/kiểu/ngữ cảnh tĩnh, tối ưu điều kiện, rồi tạo mã hoặc cấu trúc chặn thích hợp. Chi phí này thường ảnh hưởng thời gian build, xử lý bytecode, tải lớp và bộ nhớ trong giai đoạn dệt.
- **Chi phí lúc chạy (runtime matching):** kiểm tra những điều kiện chưa thể kết luận trước, chẳng hạn kiểu thực của đối tượng, trạng thái cờ hoặc luồng gọi; nếu khớp thì chạy advice. Chi phí này ảnh hưởng CPU, phân bổ bộ nhớ, độ trễ và thông lượng của ứng dụng.

**Điểm cốt lõi:** một điểm nối có thể được xác định hoàn toàn ở thời điểm dệt, xác định chắc chắn không khớp, hoặc chỉ được xác định là *ứng viên* và cần thêm phép thử khi chạy. Khi đã dệt bytecode, ứng dụng thường không phải quét lại toàn bộ pointcut và toàn bộ phương thức mỗi lần gọi; nó chạy phần mã đã được chèn tại đúng vị trí. Cách triển khai cụ thể tùy bộ dệt hoặc cơ chế chặn được sử dụng.

## 2. Các thuật ngữ và ba kết quả khớp

| Khái niệm | Vai trò | Quan hệ với chi phí |
| --- | --- | --- |
| Join point | Sự kiện trong quá trình thực thi mà mô hình AOP nhận diện | Có thể xuất hiện hàng triệu lần khi chạy |
| Join point shadow | Vị trí trong mã có khả năng phát sinh join point, ví dụ một lệnh gọi hoặc phần thân phương thức | Được duyệt/đánh giá chủ yếu khi dệt |
| Pointcut | Biểu thức chọn join point theo chữ ký, vị trí, kiểu, trạng thái, luồng điều khiển… | Có phần xét được tĩnh và phần phải xét động |
| Advice | Hành vi chạy trước, sau hoặc bao quanh join point được chọn | Chi phí khác với chi phí *khớp* pointcut |
| Residual test (điều kiện dư) | Phép thử còn cần chạy sau phân tích tĩnh | Là một phần của chi phí runtime |

Với một join point shadow cụ thể, weaver có thể phân loại:

1. **Không thể khớp:** loại bỏ luôn; không cần thêm phép thử/advice ở vị trí đó.
2. **Khớp chắc chắn:** dệt đường thực thi advice thích hợp mà không cần kiểm tra điều kiện động của pointcut đó; bản thân advice vẫn có chi phí.
3. **Có thể khớp:** dệt một điều kiện dư, chỉ gọi advice khi điều kiện đúng. Trường hợp *false* vẫn có thể phải trả chi phí kiểm tra.

Ví dụ, điều kiện chọn `execution(void demo.Worker.execute(String))` có thể được đối chiếu bằng chữ ký phương thức khi dệt. Ngược lại, `if(Flags.enabled)` phụ thuộc trạng thái lúc chạy và thường cần phép kiểm tra động. Khi hai điều kiện kết hợp bằng `&&`, tính đặc hiệu của phần tĩnh giúp weaver chỉ đặt phép kiểm tra động ở những vị trí thực sự liên quan.

## 3. Quá trình khớp tại thời điểm dệt

Một quá trình dệt mã dạng bytecode/biên dịch thường gồm các bước logic:

```text
Đọc aspect + mã chương trình
          |
          v
Phân tích pointcut (cú pháp, kiểu, tên, phạm vi)
          |
          v
Liệt kê join point shadow trong phần mã được dệt
          |
          v
Đối chiếu điều kiện tĩnh
     /        |         \
  Không      Chắc       Chưa kết luận
  khớp       chắn        được
    |          |            |
  Bỏ qua   Dệt advice    Dệt guard +
             tương ứng   advice khi guard đúng
                 \          /
                  v        v
              Sinh/biến đổi mã
```

Đây là **mô hình khái niệm**, không phải lời cam kết rằng mọi AOP engine tạo đúng cùng một thứ tự xử lý hoặc cùng một dạng bytecode.

### 3.1. Điều kiện thường xét được tĩnh

Trong cú pháp AspectJ (một ví dụ cụ thể của AOP dệt mã), những điều kiện dựa trên cấu trúc mã như `execution(...)`, `call(...)`, `within(...)`, `withincode(...)` và nhiều điều kiện dựa trên chữ ký/metadata có thể được kiểm tra lúc dệt. Ví dụ:

```aspectj
execution(void demo.Worker.execute(String))
    && within(demo.Worker)
```

Weaver có thể dựa vào chữ ký và nơi phương thức được định nghĩa để loại bỏ hầu hết vị trí không liên quan. `within` thể hiện phạm vi theo cấu trúc mã, hữu ích để giảm khối lượng dệt; nó không tự động đồng nghĩa với kiểm tra kiểu thực của đối tượng tại runtime.

Một biểu thức quá rộng như `execution(* *(..))` khiến công cụ phải xem xét rất nhiều phương thức và có thể dệt trên diện rộng. Điều này làm tăng công xử lý khi build/nạp lớp, kích thước bytecode, và đôi khi tăng số điểm chịu overhead lúc chạy. Độ rộng của tập ứng viên quan trọng hơn việc đếm số ký tự trong biểu thức.

### 3.2. Điều kiện có thể phải xét động

Các điều kiện liên quan đến dữ liệu khi chương trình đang chạy thường đòi hỏi kiểm tra thêm:

- `this(Type)`, `target(Type)`: có thể cần xét kiểu của đối tượng thực tế; một số trường hợp weaver suy ra tĩnh và loại bỏ phép thử.
- `args(Type)`: có thể cần xét kiểu thực của tham số; chỉ **gán/bind** một tham số đã biết kiểu tĩnh thường rẻ hơn kiểm tra một kiểu động chưa biết.
- `if(condition)`: chạy biểu thức điều kiện, có thể chỉ là đọc một cờ hoặc có thể gọi logic tùy ý rất tốn kém.
- `cflow(pointcut)`, `cflowbelow(pointcut)`: cần theo dõi ngữ cảnh luồng điều khiển động; thường có phí cập nhật/truy vấn trạng thái, tùy bộ dệt.
- Những điều kiện gắn với annotation trên *kiểu runtime* (ví dụ `@target`, `@args`) có thể khác với việc so khớp annotation của một khai báo đã biết lúc dệt.

Không có luật “mọi `args` đều tốn thêm một phép `instanceof`” hoặc “mọi `this` luôn xét động”: kết quả phụ thuộc chữ ký, thông tin kiểu sẵn có, ngữ cảnh join point và tối ưu của weaver/JIT.

### 3.3. Độ phức tạp lúc dệt

Một cách ước lượng thô:

```text
T_weave ≈ T_parse + T_discover_shadows + T_static_match
        + T_generate_code + T_verify/write
```

Nếu có `S` vị trí ứng viên và `P` biểu thức/nhánh pointcut liên quan, số lần xét có thể tăng theo phạm vi mã và độ phức tạp biểu thức. Không được mặc định chi phí chính xác là `O(S × P)` vì các engine có lập chỉ mục, lọc sớm, cache, chuẩn hóa boolean, hoặc chiến lược incremental khác nhau. Còn phải tính chi phí đọc/ghi bytecode và xử lý kiểu.

Trong dệt lúc biên dịch hoặc sau biên dịch, phí chủ yếu xuất hiện ở quy trình build. Trong **load-time weaving**, nó có thể xuất hiện khi lớp được nạp lần đầu và tác động đến thời gian khởi động, tải CPU khi tải lớp, bộ nhớ tạm. Không nên đánh đồng load-time weaving với một phép match lại mỗi lần phương thức thực thi.

## 4. Quá trình khớp tại runtime

Sau khi dệt, phép thử động có thể được biểu diễn bằng nhánh rẽ trong bytecode đã sinh. Mã minh họa cơ chế (***pseudocode***, không phải bytecode thực tế của một compiler cụ thể):

```java
void execute(String job) {
    if (TraceFlag.enabled) {      // residual test, nếu cần
        TraceAspect.before(job);  // advice, chỉ khi điều kiện đúng
    }
    doOriginalWork(job);
}
```

Nếu weaver xác định pointcut **luôn đúng** tại vị trí này, nó có thể không cần nhánh `if`. Nếu pointcut **không bao giờ đúng**, nó có thể không dệt mã liên quan. Nếu pointcut có nhiều điều kiện động, chương trình trả giá cho việc đọc trạng thái, phân nhánh, kiểm tra kiểu/luồng điều khiển và gắn dữ liệu ngữ cảnh.

Có thể hình dung phí bình quân cho một lời gọi đã được dệt như sau:

```text
T_after ≈ T_original + T_dispatch_or_guard
        + Pr(match) × T_advice
        + T_context_and_other_effects
```

Đây là công thức tư duy, không phải đồng nhất thức đo đạc: thứ tự tối ưu, JIT inline, nhánh dự đoán sai, cấp phát và tranh chấp tài nguyên có thể khiến các thành phần tương tác với nhau. **Điều kiện sai không đồng nghĩa chi phí bằng 0**, nhưng cũng không phải mọi join point đều phải chạy “máy dò pointcut” tổng quát.

Phân biệt ba nguồn overhead:

1. **Guard/matching:** điều kiện động, xác minh kiểu, tra cứu trạng thái.
2. **Chuyển điều khiển và tạo ngữ cảnh:** gọi advice, bao quanh lời gọi bằng `around`/`proceed`, cung cấp thông tin join point, bind đối số, boxing/cấp phát khi cần.
3. **Công việc thật của advice:** ghi log, serialize, I/O, truy cập dữ liệu, đồng bộ hóa. Thành phần thứ ba có thể lớn hơn rất nhiều so với chi phí chọn pointcut.

Do đó, một pointcut match rẻ nhưng advice ghi log đồng bộ ở mỗi lượt gọi vẫn có thể làm ứng dụng chậm nghiêm trọng.

## 5. Ví dụ AspectJ: cùng vị trí dệt, điều kiện chạy thay đổi

AspectJ được dùng **chỉ để minh họa AOP tổng quát** bằng cú pháp pointcut/advice cụ thể. Java chuẩn không biên dịch trực tiếp file `.aj`; cần trình biên dịch/dệt AspectJ (`ajc`).

**Tệp `src/demo/Main.java`:**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        Worker worker = new Worker();

        TraceFlag.enabled = true;
        worker.execute("A");

        TraceFlag.enabled = false;
        worker.execute("B");
    }
}

class Worker {
    void execute(String job) {
        System.out.println("work=" + job);
    }
}

class TraceFlag {
    static volatile boolean enabled;
}
```

**Tệp `src/demo/TraceAspect.aj`:**

```aspectj
package demo;

public aspect TraceAspect {
    pointcut monitored(String job):
        execution(void demo.Worker.execute(String))
        && args(job)
        && if(demo.TraceFlag.enabled);

    before(String job): monitored(job) {
        System.out.println("trace=" + job);
    }
}
```

Với một bản AspectJ hỗ trợ bytecode/JDK bạn đang dùng, cài `ajc` và đặt `aspectjrt.jar` trong thư mục làm việc. Ví dụ lệnh trong terminal Windows (tệp nguồn dùng các cú pháp hợp lệ với Java 17):

```powershell
ajc -source 17 -target 17 -d out -classpath "aspectjrt.jar" src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out;aspectjrt.jar" demo.Main
```

Kết quả kỳ vọng:

```text
trace=A
work=A
work=B
```

Giải thích chính xác:

- `execution(void demo.Worker.execute(String))` giới hạn ứng viên vào việc thực thi phương thức có chữ ký đã nêu: xét được bằng thông tin tĩnh.
- `args(job)` gắn đối số vào tham số advice; ở đây chữ ký là `String` nên weaver có thể biết kiểu khai báo. Binding và thử kiểu động là hai công việc khác nhau.
- `if(demo.TraceFlag.enabled)` dùng cờ `volatile` thay đổi lúc chạy: lần A advice được gọi, lần B không. Cờ `volatile` bảo đảm tính nhìn thấy giữa các luồng theo Java Memory Model; bản thân mỗi lần đọc vẫn có chi phí.
- Phí của câu lệnh `System.out.println` dùng để nhìn thấy hành vi, **không** đại diện phí thuần túy của pointcut; đừng dùng ví dụ này làm benchmark hiệu năng.

Nếu bỏ hẳn `&& if(demo.TraceFlag.enabled)` rồi dệt lại, pointcut sẽ luôn áp dụng cho cả hai lượt gọi: đầu ra khi đó có `trace=A` và `trace=B`. Đây là thay đổi **ngữ nghĩa**, không phải một phép tối ưu tương đương. Chỉ bỏ điều kiện động khi nó thực sự thừa về nghiệp vụ.

## 6. So sánh các kiểu điều kiện và điểm nóng

| Thành phần pointcut / hành vi | Khi dệt | Khi chạy | Nhận xét |
| --- | --- | --- | --- |
| `execution` / `call` theo chữ ký cụ thể | So khớp chủ yếu theo cấu trúc tĩnh | Có thể không cần guard pointcut động | Phí advice vẫn còn |
| `within` / `withincode` | Lọc theo vị trí mã nguồn/bytecode | Thường không cần kiểm tra động riêng | Giảm phạm vi dệt hiệu quả |
| Wildcard rộng `execution(* *(..))` | Nhiều shadow phải xem xét | Có thể tăng số điểm được dệt và tần suất advice | Không phải bản thân dấu `*` luôn chậm ở runtime |
| `this` / `target` / `args` theo kiểu động | Thử dùng thông tin kiểu tĩnh trước | Guard kiểu/binding nếu vẫn cần | Không áp một chi phí cố định cho mọi trường hợp |
| `if(...)` | Dệt logic điều kiện tại vị trí ứng viên | Tốn theo biểu thức và tần suất gọi | Tránh gọi hàm đắt, I/O, side effect trong predicate |
| `cflow` / `cflowbelow` | Dệt các điểm cần duy trì/truy vấn control flow | Có thể phải quản lý trạng thái ở điểm vào/ra và điểm kiểm tra | Đáng chú ý trong đoạn gọi sâu/lặp nhiều |
| `around` với `proceed` | Dệt đường chuyển điều khiển | Có thêm tầng lời gọi/ngữ cảnh, tùy tối ưu | Tách phí advice khỏi phí matching |
| Thông tin `thisJoinPoint` đầy đủ | Tùy công cụ có thể sinh dữ liệu/phương thức truy cập | Có thể phát sinh cấp phát/bọc đối số | Chỉ truy xuất khi thật sự cần |

**Lưu ý về `call` và `execution`:** `call` chọn *vị trí gọi*; `execution` chọn *lúc phương thức được thực thi*. Hai loại có thể khác nhau về phạm vi dệt, phương thức override, điểm gọi ngoài vùng có thể dệt và số lần xuất hiện. Không thay cái này bằng cái kia chỉ để tăng tốc nếu yêu cầu chức năng thay đổi.

**Lưu ý về cấu trúc Boolean:** trong một số weaver như AspectJ, pointcut được chuẩn hóa và sắp xếp phép kiểm tra để tối ưu. Viết `cheapCondition && expensiveCondition` không bảo đảm thứ tự thực thi biểu thức điều kiện luôn giống như một biểu thức Java thường. Đặc biệt, điều kiện `if` không nên tạo side effect hoặc phụ thuộc vào số lần/thứ tự gọi để bảo đảm đúng chức năng.

## 7. Số học hiệu năng: “nhỏ” nhân với “rất nhiều”

Giả sử một phương thức được gọi **20 triệu lần** trong một workload xác định và sau khi đo bằng benchmark đáng tin, một residual guard thực tế làm tăng trung bình **40 ns** cho mỗi lượt gọi so với bản tương đương không có guard:

```text
20.000.000 lần × 40 ns/lần
= 800.000.000 ns
= 0,8 giây CPU tương đương trong workload giả định
```

Con số 40 ns chỉ là **giả định để minh họa phép nhân, không phải số đo chuẩn của AOP**. Trên máy thật, độ trễ có thể thay đổi vì JIT, loại CPU, branch prediction, dữ liệu đầu vào, số luồng và contention. Nếu advice đồng thời ghi dữ liệu xuống thiết bị hoặc qua mạng, phí thực tế có thể áp đảo hoàn toàn phần guard vài chục nanogiây.

Từ đó có hai hướng cải tiến khác nhau: giảm **số điểm ứng viên/điểm được dệt** để tiết kiệm build và vùng mã bị can thiệp; giảm **số lần guard/advice được thực thi ở hot path** để tiết kiệm runtime. Một tối ưu build chưa chắc cải thiện tốc độ chạy.

## 8. Chiến lược tối ưu theo từng giai đoạn

### 8.1. Giảm chi phí dệt

1. **Thu hẹp phạm vi tĩnh:** ưu tiên chữ ký, package/type và vị trí mã chính xác. Thêm điều kiện cấu trúc như `within` khi đúng ngữ nghĩa; tránh wildcard quét toàn hệ thống nếu aspect chỉ liên quan vài thành phần.
2. **Loại trừ mã không cần dệt:** thư viện hoặc package ngoài phạm vi chức năng, mã do công cụ sinh, phần nội bộ aspect, nếu cơ chế dệt hỗ trợ cấu hình loại trừ. Cần bảo đảm exclusion không khiến mất join point bắt buộc.
3. **Phân biệt compile/post-compile/load-time weaving:** đo build sạch, build incremental và startup/nạp lớp riêng. Load-time weaving giúp linh hoạt triển khai nhưng chuyển một phần phí sang lúc nạp lớp.
4. **Theo dõi phạm vi và kích thước bytecode:** ghi nhận số join point được advice, số lớp bị sửa, thời gian weaving, kích thước artifact, lỗi xác minh/nạp lớp; không tối ưu chỉ dựa vào độ dài biểu thức.
5. **Tận dụng cơ chế incremental/cache nếu công cụ hỗ trợ:** giảm dệt lại các đơn vị không thay đổi, nhưng xác nhận cache invalidation đúng khi aspect hoặc phụ thuộc thay đổi.

### 8.2. Giảm chi phí runtime

1. **Lọc bằng điều kiện tĩnh càng nhiều càng tốt** trước khi cần `this`/`target`/`args`/`if`/`cflow`. Mục tiêu là làm phép thử động chỉ xuất hiện tại vị trí cần thiết; trình dệt có thể tối ưu thứ tự điều kiện.
2. **Giữ predicate động thuần và rẻ:** tránh regex phức tạp, quét collection, reflection lặp lại, gọi I/O hoặc locks trong điều kiện `if`. Nếu cache kết quả, phải cân nhắc vòng đời dữ liệu và tính đúng khi trạng thái đổi.
3. **Hạn chế control-flow pointcut trên đường nóng nếu không bắt buộc:** `cflow` tiện diễn đạt quan hệ gọi lồng nhau nhưng có thể cần theo dõi trạng thái liên tục; cân nhắc tín hiệu ngữ cảnh đã có hoặc thiết kế join point phù hợp hơn khi ngữ nghĩa cho phép.
4. **Giảm tạo ngữ cảnh không cần:** tránh dựng chuỗi/log, lấy cả mảng args hoặc dùng reflection ở mỗi lượt gọi chỉ để lấy một dữ kiện có sẵn. Nếu engine hỗ trợ static join point metadata, tận dụng khi đủ dùng.
5. **Giữ advice ngắn và có điều kiện hợp lý:** tránh thao tác chặn, phân bổ nhiều, ghi log đồng bộ ở tần suất cao. Đối với `around`, cân nhắc ảnh hưởng đến inline và exception path; đo trước khi kết luận.
6. **Không hi sinh tính đúng:** lựa chọn `call`/`execution`, bỏ dynamic predicate, hoặc loại lớp khỏi weaving có thể làm biến mất join point cần thiết; phải có kiểm thử hành vi bao gồm trường hợp condition true/false.

Một cải tiến pointcut có thể khiến build nhanh hơn nhưng tốc độ chạy hầu như không đổi nếu weaver vốn đã loại bỏ residual guard. Ngược lại, bỏ một predicate động ở điểm được gọi hàng triệu lần có thể có tác dụng lớn dù build không thay đổi.

## 9. Đo đạc đúng hai loại chi phí

### 9.1. Đo weaving

Giữ cố định cùng mã nguồn, JDK, phiên bản weaver, CPU và cấu hình; chạy nhiều lần mỗi cấu hình:

- **Compile-time/post-compile:** đo thời gian build sạch và build incremental, số lớp/shadow chịu weaving, kích thước và số lượng class file, bộ nhớ cực đại của quy trình build.
- **Load-time:** đo thời gian khởi động/cold class loading và số lượng lớp biến đổi; đừng tính mọi thời gian khởi động là chi phí matching pointcut.
- **Thông tin công cụ:** với AspectJ, thông tin weaving (ví dụ tùy chọn `-showWeaveInfo` khi phù hợp), log biên dịch và bytecode sau dệt giúp xác nhận một advice thật sự được chèn tại đâu.
- So sánh ít nhất một bản với **pointcut hẹp đúng ngữ nghĩa** và một bản rộng đúng ngữ nghĩa, kiểm tra số vị trí được dệt trước khi quy nguyên nhân cho thời gian dệt.

### 9.2. Đo runtime

Dùng benchmark đủ chặt chẽ cho JVM (chẳng hạn JMH), và theo dõi profiler/JFR ở workload thực:

1. **Baseline:** cùng chức năng nghiệp vụ nhưng không áp advice tại điểm đo.
2. **Static match + advice rỗng/rất nhẹ:** thấy overhead dệt/dispatch khi pointcut được xác định tĩnh.
3. **Dynamic guard + cùng advice:** thấy phần chênh lệch khi điều kiện đúng/sai, trên cùng số điểm ứng viên.
4. **Advice thật:** đo thêm chi phí log, I/O, cấp phát và lock dưới tải thực.
5. **Tải đủ đại diện:** tỷ lệ `Pr(match)`, loại đối tượng, nhiều luồng, hot/cold path, kích thước dữ liệu, startup và throughput.

Cần warm-up JVM, tránh dead-code elimination, không in console trong vòng lặp benchmark, dùng nhiều fork/iteration hợp lý và báo phân bố đo đạc (không chỉ một con số đơn). Đọc thêm allocation rate, GC, CPU sampling, branch miss nếu công cụ phần cứng hỗ trợ, p50/p95/p99 latency và throughput. Với `cflow` hoặc trạng thái theo luồng, thử cả nested calls, đệ quy và tải đồng thời; việc lan truyền ngữ cảnh qua các luồng/task không nên mặc định là tự động.

**Quan trọng:** nếu benchmark làm đổi đồng thời pointcut, nội dung advice và tần suất gọi, bạn không thể kết luận phần chênh lệch thuộc riêng về matching. Muốn đánh giá đúng, thay một biến mỗi lần và giữ tương đương về chức năng.

## 10. Các ngộ nhận và lỗi thường gặp

- **“Mỗi lời gọi đều quét toàn bộ biểu thức pointcut.”** Với dệt mã, các shadow đã được chọn trước; lúc chạy chỉ còn những guard đã được sinh ra (nếu có). Một số cơ chế chặn động có mô hình khác và cần đo riêng.
- **“Pointcut có wildcard luôn tốn nhiều nanogiây hơn mỗi lời gọi.”** Wildcard ảnh hưởng nhiều đến tập shadow được lựa chọn và chi phí dệt; runtime phụ thuộc mã cuối cùng tại từng shadow.
- **“Đặt `if` sau `&&` bảo đảm nó chạy sau.”** Trình dệt có thể tái sắp xếp/loại bỏ điều kiện. Không tạo side effect trong pointcut.
- **“Chỉ tắt logging là đã đo được overhead pointcut.”** Bạn vẫn có thể đang đo guard, binding, dispatch, allocation hoặc cách tối ưu JIT khác nhau.
- **“`cflow` giống một phép so chữ ký.”** Nó dùng ngữ cảnh luồng điều khiển runtime, có thể cần duy trì trạng thái từ các vị trí vào/ra, không chỉ so tên hàm.
- **“Tất cả `this`, `target` và `args` luôn gọi reflection.”** Thường là kiểm tra kiểu đơn giản hoặc được giải quyết tĩnh; không suy diễn có reflection nếu chưa xem mã dệt.
- **“Không có advice chạy thì không có overhead.”** Tại shadow còn guard, lần không match vẫn có thể chạy phép kiểm tra.
- **“Dùng `call` thay `execution` luôn tương đương.”** Chúng chọn loại join point khác nhau; kết quả thay đổi với vị trí gọi, kế thừa/override và phạm vi mã được dệt.
- **“Build nhanh đồng nghĩa runtime nhanh.”** Chi phí xét tĩnh nằm ở build/load; chi phí xét động và advice nằm ở mỗi lần thực thi.
- **“Có thể suy hiệu năng từ một lần `System.nanoTime()`.”** Sai số thời gian, JVM warm-up, GC và tối ưu có thể lớn hơn chi phí cần đo.

## 11. Checklist khi thiết kế pointcut hiệu năng cao

1. **Nêu đúng join point cần chọn:** gọi hay thực thi? Kiểu khai báo nào, package nào, trường hợp kế thừa nào?
2. **Viết bộ lọc tĩnh có nghĩa:** chữ ký chính xác, `within`/`withincode` khi phù hợp; tránh quét rộng chỉ vì thuận tiện.
3. **Liệt kê phần bắt buộc động:** kiểu runtime, giá trị args, cờ điều kiện, call stack/control flow; kiểm tra xem mỗi điều kiện có thể được xác định tĩnh trong trường hợp cụ thể hay không.
4. **Ước lượng tần suất:** phương thức vài lần lúc startup khác hẳn phương thức vài triệu lần/giây.
5. **Đo riêng weaving, guard, dispatch và advice:** dùng mã sinh ra, thống kê số shadow và benchmark đối chứng.
6. **Kiểm thử tính đúng:** cả nhánh khớp/không khớp; nạp lớp trễ, subtype, đồng thời, exception và đường gọi khác nhau.
7. **Giữ tối ưu chỉ khi số đo cải thiện:** cùng workload, cùng cấu hình, cùng semantics; theo dõi cả thời gian build, bộ nhớ, thông lượng, latency và độ ổn định.

**Kết luận:** tối ưu pointcut AOP là phân biệt việc **xét ứng viên một lần khi dệt** với việc **kiểm tra điều kiện dư mỗi lần chạy**. Hãy dùng thông tin tĩnh để giới hạn nơi dệt, chỉ giữ điều kiện động thật sự cần, và đo overhead matching tách khỏi công việc của advice. Cách đo này cho biết nên tối ưu build/startup, hot path, hay chính phần advice.

## Tài liệu tham khảo

- Eclipse AspectJ Programming Guide — Pointcuts, advice và tối ưu matching: https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html
- Eclipse AspectJ Pointcut Debugging — lọc theo `within`, phân biệt điều kiện tĩnh/động: https://eclipse.dev/aspectj/doc/latest/pdguide/pointcuts.html
- Eclipse AspectJ Language — cú pháp `execution`, `call`, `if`, `cflow`: https://eclipse.dev/aspectj/doc/latest/progguide/language.html
