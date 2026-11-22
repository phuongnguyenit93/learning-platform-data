# Tối ưu phạm vi can thiệp trước khi tối ưu vi mô trong AOP

**Tối ưu phạm vi can thiệp** nghĩa là quyết định chính xác *join point* nào thực sự cần áp dụng advice, với điều kiện nào và trong giai đoạn nào của chương trình. Đây thường là bước ưu tiên trước khi cố giảm vài nanosecond của reflection, proxy dispatch, cấp phát context hay lệnh bên trong advice. Một advice chạy nhanh vẫn gây lãng phí nếu được kích hoạt hàng triệu lần ở những vị trí không cần chức năng của nó.

Nguyên tắc cốt lõi: **chỉ làm công việc xuyên suốt ở những điểm thực thi mà yêu cầu chức năng đòi hỏi, rồi mới tối ưu chi phí của mỗi lần thực hiện**. Việc thu hẹp phải bảo toàn các bất biến như kiểm tra quyền, audit bắt buộc, cleanup, giao dịch và xử lý lỗi. Không cắt bớt join point chỉ vì nó đang tốn CPU nếu việc cắt đó làm mất ngữ nghĩa.

Bài này nghiên cứu AOP tổng quát: pointcut, advice, join point, proxy, weaving và những lựa chọn hiệu năng có thể áp dụng tùy cơ chế triển khai. Các ví dụ Java 17+ dùng proxy động của JDK để minh họa một cơ chế cụ thể, không đại diện cho mọi hệ thống AOP.

## 1. Tại sao phải xét phạm vi trước các tối ưu nhỏ?

Một yêu cầu theo dõi nghiệp vụ chỉ cần ghi nhận **thao tác thay đổi trạng thái**. Nếu pointcut bắt cả thao tác chỉ đọc, getter, toán tử tính toán hoặc helper được gọi trong vòng lặp, advice sẽ phải làm việc ở rất nhiều chỗ không có giá trị.

Ví dụ mô hình:

```text
10.000.000 lời gọi phương thức / phút
        │
        ├── 9.800.000 lời gọi chỉ đọc hoặc helper (không cần audit)
        └──   200.000 thao tác thay đổi trạng thái (cần audit)

Pointcut quá rộng: advice audit chạy 10.000.000 lần/phút
Pointcut đúng phạm vi: advice audit chạy 200.000 lần/phút
```

Trong ví dụ giả định này, chọn đúng phạm vi giảm **98% số lần chạy audit advice**. Tuy nhiên, điều đó **không tự động đồng nghĩa giảm 98% CPU, latency hoặc tổng chi phí AOP**: chi phí dispatch, matcher, xử lý nghiệp vụ, tần suất đa dạng và các yếu tố JVM vẫn khác nhau.

So sánh hai cách tư duy:

- **Tối ưu vi mô:** giữ nguyên 10 triệu lần advice, cố giảm một thao tác cấp phát hoặc thay API gọi động bằng cách khác.
- **Tối ưu phạm vi:** nhận ra chỉ 200 nghìn điểm thực thi cần audit, chọn đúng 200 nghìn điểm đó, rồi profile xem những lần còn lại có nút thắt gì.

Khi mục tiêu là giảm overhead, thứ tự thường hợp lý là: **đúng yêu cầu → đúng join point → đúng ngữ nghĩa → đo thực tế → tối ưu chi phí bên trong**.

## 2. Phạm vi can thiệp có nhiều lớp

| Phạm vi | Câu hỏi thiết kế | Ví dụ |
|---|---|---|
| Loại join point | Can thiệp vào gọi phương thức, thực thi phương thức hay điểm thực thi khác? | Theo dõi mỗi lần thực thi thao tác, thay vì mọi vị trí gọi nó |
| Module / package / kiểu | Những thành phần nào thuộc nghiệp vụ cần áp dụng? | Chỉ các kiểu thực hiện cập nhật tồn kho |
| Phương thức / chữ ký | Những thao tác nào thực sự cần advice? | `reserve(...)` và `release(...)`; loại bỏ `find(...)` |
| Annotation / metadata | Có hợp đồng đánh dấu rõ các thao tác cần chính sách? | Một annotation do dự án định nghĩa cho thao tác nhạy cảm |
| Điều kiện runtime | Có cần lọc dựa trên đối số, người gọi hoặc trạng thái? | Chỉ xử lý khi thay đổi vượt ngưỡng được định nghĩa |
| Vị trí môi trường / đường chạy | Phạm vi nào là bắt buộc ở production, test hoặc công cụ? | Chỉ bật profiling chi tiết ở thí nghiệm; audit vẫn giữ |
| Thời điểm / mức lấy mẫu | Có được phép chỉ xử lý một phần sự kiện? | Sampling tracing với tỷ lệ có kiểm soát, **không** sampling audit bắt buộc |

Không nên dồn mọi lọc vào một điều kiện trong advice. Nếu một phần điều kiện có thể được quyết định trước khi runtime phải tạo context, hệ thống có thể giảm cả công việc chọn advice. Ngược lại, nếu cần dữ liệu theo từng lời gọi thì điều kiện động vẫn phải được đánh giá ở mỗi điểm phù hợp.

### 2.1. Thu hẹp pointcut bằng điều kiện tĩnh

Điều kiện tĩnh là điều kiện có thể kết luận từ kiểu, chữ ký, metadata hoặc quan hệ mã chương trình đã xác định. Chẳng hạn:

```text
selected(method) =
    method thuộc nhóm "InventoryOperations"
    AND method.name thuộc {"reserve", "release"}
    AND method.returnType phù hợp hợp đồng
```

Đây là **pseudocode khái niệm**, không phải cú pháp của một công cụ AOP cụ thể.

Nếu bộ máy có khả năng phân tích trước các điều kiện này, nó có thể dựng bảng các join point được chọn khi thiết lập hoặc khi weave. Có thể giảm số lần kiểm tra pointcut, số lần vào advice và nhu cầu tạo invocation context. Mức giảm dispatch phụ thuộc phương pháp triển khai: với proxy bọc nguyên đối tượng, các phương thức không được chọn vẫn có thể đi qua proxy handler.

### 2.2. Thu hẹp bằng điều kiện động

Ví dụ chỉ kích hoạt một cảnh báo khi `amount > 1_000_000`:

```text
selected(call) =
    method.name = "transfer"
    AND call.arguments.amount > 1_000_000
```

Điều kiện tên phương thức là tĩnh; giá trị `amount` là động. Ngay cả khi metadata được cache, mỗi lần gọi `transfer` vẫn phải kiểm tra dữ liệu thực tế nếu chính sách quy định như vậy. Việc kiểm tra số nguyên có thể rẻ; nhưng nếu điều kiện gọi cơ sở dữ liệu, xây biểu thức chính quy mới hoặc giải mã JSON thì nó không còn là bộ lọc rẻ nữa.

Một chiến lược thường hữu ích là **lọc tĩnh trước, lọc động sau**:

```text
Chưa thuộc kiểu/phương thức mục tiêu?
  └── Bỏ qua xử lý advice và điều kiện động

Thuộc tập ứng viên tĩnh?
  └── Kiểm tra dữ liệu invocation cần thiết
        ├── Không khớp → không chạy advice
        └── Khớp → thực hiện advice
```

Vẫn phải xét semantics: điều kiện bảo mật hoặc quản lý giao dịch thường cần kiểm tra cho tất cả thao tác thuộc miền áp dụng, không được bỏ qua vì tối ưu một nhánh.

## 3. Mô hình định lượng để ưu tiên

Gọi:

- `N`: số join point có khả năng đi vào cơ chế chặn trong một khoảng đo.
- `p`: tỷ lệ join point thực sự cần advice, từ 0 đến 1.
- `c_entry`: chi phí trung bình đi vào proxy/dispatch hoặc đường kiểm tra tương đương.
- `c_match`: chi phí trung bình xác định có khớp pointcut hay không.
- `c_advice`: chi phí trung bình chạy advice tại điểm khớp, chưa kể logic nghiệp vụ gốc.

Ước tính đơn giản:

```text
Chi phí can thiệp ≈ N × (c_entry + c_match)
                  + N × p × c_advice
```

Đây là **mô hình tư duy**, không phải công thức đo chính xác từng phép cộng. JIT, branching, cache, đa hình, GC, contention, phân phối input và advice lồng nhau khiến các thành phần tương tác; một số cơ chế weaving có thể đưa chi phí matching tĩnh về thời điểm build/load.

Ví dụ giả định:

```text
N = 2.000.000 lời gọi / giây
p = 0,05 (5% cần advice)
c_advice = 500 ns mỗi lời gọi khớp

Advice trên toàn bộ N: 2.000.000 × 500 ns ≈ 1 CPU-second/second
Advice trên 5% N:        100.000 × 500 ns ≈ 0,05 CPU-second/second
```

Chỉ ví dụ hóa thời gian CPU cộng dồn của **nội dung advice** khi mỗi lượt cùng tốn 500 ns; nó không khẳng định tiết kiệm toàn hệ thống 95% CPU, cũng không tính đường dispatch hoặc matching. Nếu bộ lọc động thêm 300 ns trên *toàn bộ* N, chi phí lọc mới có thể lấn át khoản tiết kiệm 500 ns trên các lượt bị loại. Vì vậy cần đo cả **tần suất**, **độ chọn lọc** và **chi phí của chính bộ lọc**.

### Định lượng bằng bảng công việc

| Loại thao tác | Tần suất giả định | Advice cần chạy? | Ưu tiên kiểm tra |
|---|---:|---|---|
| Getter hoặc helper tính toán | 5.000.000 lượt/phút | Không | Loại khỏi pointcut rộng |
| Đọc thông tin bình thường | 300.000 lượt/phút | Chỉ khi có yêu cầu truy vết cụ thể | Tránh audit thay đổi dữ liệu |
| Cập nhật thông tin nhạy cảm | 20.000 lượt/phút | Có, bắt buộc | Giữ đầy đủ xử lý và chứng cứ |
| Thực hiện giao dịch chuyển tiền | 5.000 lượt/phút | Có, bắt buộc | Đúng biên giao dịch, bảo mật, ngoại lệ |
| Thu thập tracing chi tiết | Tùy tải | Có thể lấy mẫu khi chính sách cho phép | Đo tính đại diện và tail latency |

Đây là những tần suất để **minh họa phương pháp**; bài học không đưa ra benchmark thực tế. Không được dùng bảng để tự bỏ qua chức năng bắt buộc vì nó có tần suất cao.

## 4. Ví dụ Java 17+: chọn phương thức cần advice

Ví dụ này so sánh **pointcut rộng** (mọi lời gọi trên interface đều chạy advice đếm) với **pointcut hẹp** (chỉ thao tác `reserve` chạy advice đếm). Cả hai vẫn đi qua proxy; do đó ví dụ chứng minh giảm **số lần thực hiện advice**, không chứng minh loại bỏ hết chi phí proxy.

Tạo file `SelectiveAopDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

public class SelectiveAopDemo {
    public interface Inventory {
        int find(int sku);
        int reserve(int sku, int quantity);
    }

    static final class InventoryImpl implements Inventory {
        @Override
        public int find(int sku) {
            return sku * 2;
        }

        @Override
        public int reserve(int sku, int quantity) {
            return sku * 2 - quantity;
        }
    }

    static Inventory instrument(
            Inventory target,
            Predicate<Method> pointcut,
            AtomicInteger adviceHits) {

        return (Inventory) Proxy.newProxyInstance(
            Inventory.class.getClassLoader(),
            new Class<?>[] { Inventory.class },
            (proxy, method, arguments) -> {
                if (pointcut.test(method)) {
                    adviceHits.incrementAndGet();
                }

                try {
                    return method.invoke(target, arguments);
                } catch (InvocationTargetException e) {
                    throw e.getCause();
                }
            }
        );
    }

    public static void main(String[] args) {
        Inventory target = new InventoryImpl();

        AtomicInteger broadHits = new AtomicInteger();
        Inventory broad = instrument(
            target, method -> true, broadHits
        );

        AtomicInteger narrowHits = new AtomicInteger();
        Inventory narrow = instrument(
            target,
            method -> method.getName().equals("reserve"),
            narrowHits
        );

        System.out.println(
            "Rộng: " + broad.find(7) + ", "
            + broad.reserve(7, 3) + ", " + broad.find(8)
        );
        System.out.println(
            "Hẹp: " + narrow.find(7) + ", "
            + narrow.reserve(7, 3) + ", " + narrow.find(8)
        );
        System.out.println("Advice rộng: " + broadHits.get());
        System.out.println("Advice hẹp: " + narrowHits.get());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac SelectiveAopDemo.java
java SelectiveAopDemo
```

Stdout chính xác:

```text
Rộng: 14, 11, 16
Hẹp: 14, 11, 16
Advice rộng: 3
Advice hẹp: 1
```

Vì `find(7)=14`, `reserve(7,3)=11` và `find(8)=16`, hai đường gọi giữ cùng kết quả nghiệp vụ. Với pointcut rộng, advice chạy ba lần; với pointcut hẹp, advice chỉ chạy một lần. Cần chú ý:

1. **Mọi lời gọi trên cả hai proxy đều vào `InvocationHandler`**, kiểm tra predicate rồi gọi target bằng `Method.invoke`. Như vậy phương thức `find` trên proxy hẹp vẫn có phí dispatch/matching.
2. Advice trong ví dụ chỉ tăng `AtomicInteger`; đây là hành động quan sát để đếm lượt, cũng tiêu tốn tài nguyên. Nó không thể đại diện cho chi phí của logging, audit thật hoặc tracing I/O.
3. `method.getName().equals("reserve")` là cách chọn để học; hệ thống lớn cần xét overload, kiểu khai báo, annotation, đường triển khai và chính sách chặn các lời gọi liên quan. Chỉ so tên có thể chọn sai join point.
4. `Method.invoke` có thể bọc ngoại lệ từ target trong `InvocationTargetException`, nên handler mở wrapper trước khi ném lại. Các ngoại lệ checked ngoài chữ ký interface còn chịu quy tắc của dynamic proxy.
5. Chương trình không đo tốc độ hoặc cấp phát. Để so sánh hiệu năng, phải có benchmark với cùng chức năng, warm-up và phép đo allocation/latency.

Nếu cơ chế được chọn hỗ trợ weave advice **chỉ vào phương thức `reserve`**, `find` có thể không cần đi qua handler tương đương. Ngược lại, nếu áp proxy cho toàn bộ một interface, thu hẹp predicate vẫn có thể cần xét chi phí vào proxy trên mọi method.

## 5. Từ “pointcut rộng” đến “pointcut đúng”: phương pháp thiết kế

### Bước 1 — Xác định yêu cầu bắt buộc trước khi định vị join point

Hỏi cụ thể:

- Advice thực thi yêu cầu nào: quyền truy cập, audit, chuẩn hóa lỗi, đo thời gian, log chẩn đoán hay caching?
- Có quy tắc pháp lý/nghiệp vụ nào yêu cầu không bỏ sót bất kỳ thao tác thuộc miền bảo vệ?
- Đơn vị cần quan sát là *mỗi lần gọi phương thức*, *mỗi giao dịch nghiệp vụ*, *mỗi request* hay *mỗi sự kiện thay đổi trạng thái*?
- Yêu cầu gồm đường thành công, đường lỗi, retry, nested call và xử lý bất đồng bộ như thế nào?
- Những dữ liệu hoặc kết quả nào cần có trong context, tại thời điểm nào?

Ví dụ nếu muốn audit một **thao tác thay đổi trạng thái**, can thiệp vào mọi getter không đúng mục tiêu; nhưng nếu muốn kiểm tra quyền đọc dữ liệu nhạy cảm, loại hết getter/read operation sẽ tạo lỗ hổng. Phải xác định yêu cầu riêng của từng loại advice.

### Bước 2 — Vẽ ranh giới nghiệp vụ, danh sách điểm bắt buộc và điểm không cần

Dùng một ma trận trước khi chọn predicate:

| Nhóm join point | Advice liên quan | Mức bắt buộc | Lý do |
|---|---|---|---|
| Lệnh thay đổi dữ liệu nhạy cảm | Audit, kiểm tra quyền | Bắt buộc | Bảo toàn chứng cứ và chính sách truy cập |
| Gọi dịch vụ bên ngoài | Timing/tracing | Phụ thuộc mục tiêu quan sát | Theo dõi độ trễ của hệ thống phụ thuộc |
| Hàm biến đổi thuần (pure function) | Không cần logging toàn bộ | Thường loại trừ | Ít thông tin hữu ích, có thể là hot path |
| Getter hoặc hàm tiện ích | Không dùng audit thay đổi dữ liệu | Thường loại trừ | Tránh bắt mọi lời gọi nhỏ |
| Đường lỗi của thao tác quan trọng | Cleanup, xử lý ngoại lệ, audit lỗi | Bắt buộc khi hợp đồng yêu cầu | Không bỏ sót thất bại |
| Job thử nghiệm nội bộ | Profiling chi tiết | Có thể cấu hình | Không nhất thiết chạy liên tục |

Ma trận cần được kiểm tra với người sở hữu nghiệp vụ và người chịu trách nhiệm bảo mật/tuân thủ khi advice liên quan đến bất biến quan trọng. Nhiệm vụ tối ưu là **giảm xử lý thừa trong phần được phép giảm**.

### Bước 3 — Dùng tập chọn tĩnh nhỏ nhất nhưng bao phủ đủ

Ví dụ về điều kiện khái niệm:

```text
candidate(method) =
    declaringType thuộc nhóm thay đổi trạng thái
    AND method thuộc API nghiệp vụ được kiểm soát
    AND method không nằm trong nhóm helper thuần túy
```

Khi có annotation đánh dấu rõ ý định can thiệp, nó có thể dễ kiểm soát hơn quy tắc dựa vào prefix `get*` hoặc `save*`. Nhưng annotation cũng phải được áp đúng vị trí; cần kiểm tra sự khác biệt giữa annotation trên interface, implementation, phương thức override, kế thừa hoặc meta-annotation tùy bộ máy AOP.

Không nên xây dựng hàng chục pattern mơ hồ trên tên class chỉ để bắt được một vài lời gọi. Nếu hệ thống cho phép, soát tập join point được chọn ngay lúc cấu hình, rồi biến tập đó thành một phần của kiểm thử.

### Bước 4 — Thêm bộ lọc động chỉ khi thật sự cần

Giả sử cùng phương thức cập nhật có những trường hợp cần tracing chi tiết:

```text
staticCandidate = method thuộc nhóm update
dynamicMatch   = staticCandidate
                 AND request có cờ chẩn đoán được phép
```

Thứ tự này tránh tạo context chi tiết hoặc tính điều kiện đắt đỏ cho các phương thức vốn không thuộc tập ứng viên. Tuy nhiên, với một proxy luôn nhận lời gọi, kiểm tra tĩnh có thể vẫn diễn ra ở runtime nếu implementation không precompute được.

Đừng sử dụng ngoại lệ để làm luồng chọn thông thường; đừng parse chuỗi JSON hay truy vấn dữ liệu ở mỗi getter chỉ để quyết định có log hay không. Nếu có thể, chuẩn bị dữ liệu và điều kiện rẻ hơn tại biên nghiệp vụ.

### Bước 5 — Kiểm tra bao phủ thật, không chỉ nhìn biểu thức

“Pointcut trông đúng” chưa chứng minh mọi đường gọi cần thiết được can thiệp. Những trường hợp dễ bỏ sót:

- Lời gọi nội bộ trong cùng đối tượng (*self-invocation*) không đi qua proxy ở một số cách triển khai.
- Phương thức final/private/constructor hoặc static method có khả năng được chặn khác nhau theo cơ chế proxy/weaving.
- Interface và phương thức implementation có metadata hoặc annotation không giống nhau.
- Overload/trùng tên phương thức khiến lọc tên đơn giản quá rộng.
- Lớp được nạp bằng class loader khác hoặc proxy sinh mã có quy tắc dispatch riêng.
- Lời gọi async hoặc callback chạy ở context khác; kiểm tra quyền/trace có thể cần propagation.
- Retry có thể gây nhiều lần thực thi join point cho một thao tác nghiệp vụ; audit nên xác định rõ ghi mỗi attempt hay mỗi business operation.
- Advice around có thể short-circuit, gọi `proceed()` một lần hoặc nhiều lần; đếm “join point đi vào” và đếm “target thực thi” có thể khác.

Ở những đường quan trọng, viết kiểm thử **bao phủ hành vi** (advice có chạy khi phải chạy, không chạy khi không cần) thay vì chỉ kiểm tra tên method có khớp chuỗi.

## 6. Scope của proxy, pointcut và advice không đồng nhất

Ba lớp cần tách:

**Lớp A: Đối tượng nào được instrument?** Nếu cả một kiểu đối tượng bị bọc bằng proxy, nhiều phương thức của kiểu đó vẫn đi qua một tầng dispatch dù không cần chạy advice. Thu hẹp tập đối tượng được áp proxy có thể giảm phần overhead chung, nhưng phải giữ khả năng chặn tất cả đường gọi quan trọng.

**Lớp B: Join point nào được xét là ứng viên?** Bộ máy có thể dựng trước danh sách method được chọn hoặc phải so khớp ở runtime. Lọc ứng viên bằng metadata tĩnh sớm giúp tránh kiểm tra động trên các method không cần thiết.

**Lớp C: Trong ứng viên, khi nào thực sự chạy advice?** Đây là nơi quyết định dựa vào đối số hoặc trạng thái runtime. Khi không thể tránh đánh giá động, hãy làm phép kiểm tra rẻ và không có side effect ngoài mong muốn.

Ví dụ:

```text
Caller
  │
  ├─ Đối tượng không cần AOP ────────────────> Target trực tiếp
  │
  └─ Đối tượng được instrument
        │
        ▼
      Proxy / đường chặn (vẫn có thể tốn dispatch)
        │
        ├─ Method ngoài tập ứng viên ────────> Target
        │
        └─ Method trong tập ứng viên
              │
              ├─ Không khớp điều kiện động ─> Target
              │
              └─ Khớp ───────> Advice ─────> Target
```

Sơ đồ chỉ minh họa trường hợp advice cho phép chuyển tiếp đến target một lần. Với advice có quyền bỏ qua hoặc retry, đường điều khiển có thể khác.

Sự phân biệt này giúp tránh báo cáo sai: khi chỉ giảm số lượt advice nhưng proxy và matcher vẫn chạy, cần báo **advice invocations giảm**; không thể tự gọi đó là “bỏ hoàn toàn overhead AOP”.

## 7. Chọn điểm can thiệp ở tầng nghiệp vụ phù hợp

### 7.1. Không instrument mọi helper trong chuỗi gọi

Giả sử một thao tác:

```text
placeOrder()
  ├─ validateInput()
  ├─ calculateTotal()
  │    ├─ readUnitPrice()
  │    └─ applyDiscount()
  ├─ reserveInventory()
  └─ recordOrder()
```

Nếu yêu cầu chỉ đo thời gian **toàn bộ thao tác đặt hàng**, instrument `placeOrder()` có thể phù hợp hơn việc bọc tất cả hàm con; điều này giảm số lần chạy advice và tránh các khoảng đo lồng nhau. Nếu mục tiêu thật sự là tìm nơi chậm, có thể instrument chọn lọc `reserveInventory()` hoặc `recordOrder()` trong thời gian điều tra.

Nhưng nếu bảo mật yêu cầu kiểm soát từng thao tác tác động tồn kho, chỉ instrument `placeOrder()` sẽ không đủ nếu `reserveInventory()` còn có đường gọi khác. Phải xét **biên nghiệp vụ nào là authoritative**, những caller nào có thể đi qua biên đó và chính sách nào phải được bảo vệ độc lập.

### 7.2. Giảm dữ liệu context sau khi đã chọn đúng điểm

Sau khi thu hẹp pointcut, mới xem advice cần dữ liệu gì. Timing advice có thể chỉ cần thời điểm bắt đầu và nhãn method ổn định, thay vì clone toàn bộ `Object[]`. Audit bắt buộc có thể cần dữ liệu actor, hành động và outcome; bỏ các trường đó là thay đổi chức năng. Cách quyết định phụ thuộc hợp đồng advice.

Tối ưu phạm vi và tối ưu context có quan hệ: ít join point hơn → ít lần phải đóng gói context; context nhỏ hơn → ít chi phí trên những join point còn lại.

### 7.3. Không lạm dụng sampling cho công việc bắt buộc

Sampling phù hợp với một số dạng telemetry khi không cần ghi nhận từng sự kiện, như trace phân tán để phân tích xu hướng. Nhưng một policy kiểm tra quyền, cleanup resource hoặc audit bắt buộc không thể tự bỏ qua 99% chỉ để tăng throughput.

Với tracing sampling, cần ghi rõ cách chọn mẫu, tính đại diện, ảnh hưởng của lỗi hiếm, parent-child trace, tỷ lệ lưu giữ và cách đọc số liệu. Lấy mẫu 1% đồng nghĩa có thể bỏ lỡ sự kiện hiếm, nên không biến kết quả mẫu thành lời khẳng định bao phủ tuyệt đối.

## 8. Đo trước và sau bằng chỉ số phản ánh phạm vi

Chỉ đo ns/op của một proxy không đủ để thấy tác động từ giảm số lần thực thi advice. Nên thu thập:

| Chỉ số | Ý nghĩa | Dấu hiệu cần lưu ý |
|---|---|---|
| Tổng số join point có thể bị bắt | Quy mô đường gọi | Có bị tính cả đường thực thi không liên quan? |
| Số lần matcher đánh giá | Chi phí chọn pointcut | Matcher động có chạy ở mọi lời gọi? |
| Số lần advice thực sự chạy | Độ chọn lọc của phạm vi | Có giảm sau chỉnh pointcut? |
| Tỷ lệ advice chạy / join point ứng viên | Mức độ lọc | Quá thấp có thể cho thấy lọc động đắt ở phạm vi rộng |
| CPU time của advice | Tài nguyên của chính xử lý xuyên suốt | Chú ý thời gian chờ I/O không bằng CPU time |
| Latency p50/p95/p99 | Trải nghiệm và SLO | Điểm nghẽn có thể lộ ở tail latency |
| Allocated bytes/op, allocation rate | Áp lực cấp phát | Có giảm khi bỏ context cho các điểm không cần? |
| GC pauses, contention, queue depth | Hậu quả gián tiếp | Async logging và lock có thể áp đảo chi phí dispatch |
| Số sự kiện bắt buộc bị bỏ sót | Độ đúng đắn | Phải bằng 0 theo chính sách kiểm chứng |

Khi đo, phân loại riêng các phương thức thuộc tập *must intercept*, *optional observability* và *must exclude* để nhìn thấy cả hiệu năng lẫn thay đổi bao phủ.

### Cách tiến hành thí nghiệm

1. **Đường cơ sở:** chạy cùng workload với pointcut hiện tại; ghi advice count, CPU, latency, GC và chức năng quan sát được.
2. **Thiết lập ma trận bao phủ:** liệt kê join point bắt buộc và các đường gọi khác có thể đi đến cùng hành vi nghiệp vụ.
3. **Thu hẹp từng bước:** chỉnh điều kiện tĩnh trước; chỉ dùng điều kiện động khi yêu cầu buộc phải phụ thuộc runtime state.
4. **Kiểm chứng chức năng:** thử cả đường thành công, ngoại lệ, nested call, retry, concurrent call và async nếu hệ thống có.
5. **Kiểm tra đường thực thi:** bằng counter, log chẩn đoán có kiểm soát hoặc profiler xác định advice nào thực sự chạy; lưu ý công cụ đo cũng có overhead.
6. **Chạy benchmark:** cho microbenchmark dùng JMH với warm-up, nhiều iterations/forks và kết quả không bị JVM loại bỏ; đồng thời chạy test tải hệ thống với concurrency đại diện.
7. **So sánh:** báo cả thay đổi tuyệt đối và tương đối cho advice count, CPU, throughput, p95/p99, allocation và lỗi nghiệp vụ; kiểm tra mức tin cậy của số liệu.
8. **Chỉ sau khi xác nhận phạm vi đúng**, tối ưu phí mỗi lần gọi: metadata caching, chuẩn bị chain, hạn chế clone arguments, đường dispatch phù hợp, log formatting, lock hoặc batching telemetry.

JMH dùng để định lượng chi phí từng lời gọi; **tổng lợi ích của thu hẹp pointcut** thường còn phụ thuộc tần suất các loại lời gọi trong ứng dụng thật. Một benchmark luôn gọi một method duy nhất có thể không biểu diễn được lợi ích khi loại bỏ hàng triệu getter trong workload sản xuất.

## 9. Những ràng buộc khi quyết định phạm vi

### Chi phí lọc cũng là chi phí

Một pointcut “chỉ chạy advice ở 1% lời gọi” có thể vẫn lãng phí nếu phải thực hiện phép lọc tốn 2 ms ở mọi lời gọi. Nếu điều kiện tĩnh có thể precompute, nên chuẩn bị trước. Nếu phải kiểm tra dữ liệu runtime, tránh truy vấn I/O hoặc xây object phức tạp chỉ để xác định có chạy advice hay không.

Ví dụ tính toán (giả định):

```text
1.000.000 lần kiểm tra × 2 µs = 2 giây công việc cộng dồn
10.000 lần advice     × 5 µs = 0,05 giây công việc cộng dồn
```

Đường kiểm tra phạm vi đã đắt hơn nhiều so với advice còn lại. Một cách chọn khác như kiểm tra rẻ từ dữ liệu đã có tại biên nghiệp vụ có thể có lợi hơn, nếu bảo toàn đúng chính sách.

### Khả năng tối ưu của JVM không đồng nhất

Một wrapper ngắn có thể được JIT inline, trong khi chuỗi dispatch đa hình, reflection hoặc kiểm tra trạng thái động có thể hạn chế một số tối ưu. Cũng có trường hợp runtime đã tối ưu khá tốt nên lợi ích giảm vi mô nhỏ. **Không gán chi phí cố định cho “mỗi proxy” hoặc “mỗi advice”** trên mọi JDK.

### Thứ tự advice ảnh hưởng semantics

Nếu một advice kiểm tra quyền chạy trước audit, các yêu cầu audit thất bại có thể được xử lý khác khi đảo thứ tự. Nếu chỉ instrument ở biên thành công mà không bắt đường ngoại lệ, có thể mất dữ liệu quan trọng. Không đổi thứ tự hoặc loại một advice khỏi path mà chưa hiểu các hiệu ứng before/after/around và cleanup.

### Thay cơ chế can thiệp có thể đổi tập join point

Proxy, decorator, runtime interception và bytecode weaving không nhất thiết có cùng tập điểm thực thi quan sát được. Tối ưu bằng cách chuyển cơ chế AOP có thể làm lộ hoặc bỏ sót self-invocation, phương thức không thể override, đường constructor hoặc điểm gọi khác. Chỉ so hiệu năng khi hai cách thực hiện **cùng nghĩa quan sát được** và có bảng đối chiếu điểm chặn.

## 10. Các lỗi thường gặp khi “thu hẹp”

1. **Lọc theo tên phương thức quá đơn giản:** `save*` có thể chọn nhầm phương thức helper hoặc bỏ sót `commit`, `reserve`. Dùng hợp đồng rõ ràng và kiểm tra overload/kiểu.
2. **Tin rằng loại advice nghĩa là loại proxy:** handler vẫn có thể chạy trước khi biết không khớp.
3. **Đưa bộ lọc động nặng vào mọi lời gọi:** tiết kiệm chi phí advice nhưng trả nhiều hơn cho matching.
4. **Bỏ điểm kiểm tra quyền do tần suất lớn:** gây lỗ hổng bảo mật; kiểm soát quyền cần dựa vào biên thực thi có trách nhiệm.
5. **Chỉ kiểm tra happy path:** bỏ sót exception, retry hoặc transaction rollback.
6. **Không xét lời gọi nội bộ:** các cơ chế proxy có thể không thấy đường không đi qua proxy.
7. **Tối ưu bằng sampling audit bắt buộc:** đánh đổi chức năng và bằng chứng nghiệp vụ.
8. **Thêm nhiều điều kiện loại trừ theo cảm tính:** khiến cấu hình khó hiểu, khó review và không kiểm chứng được độ bao phủ.
9. **Cho rằng annotation luôn được nhìn thấy ở mọi override:** việc tra cứu annotation phụ thuộc vị trí khai báo, cách kế thừa và cơ chế instrument.
10. **Chỉ nhìn mean latency:** tail latency, contention, async queue và GC có thể mới là vấn đề.
11. **Benchmark khác ngữ nghĩa:** phiên bản hẹp mất một side effect bắt buộc thì nhanh hơn cũng không hợp lệ.
12. **Chỉ đo số lần advice chạy:** không đo lỗi bị bỏ qua, matcher cost và dispatch còn lại thì kết luận hiệu năng thiếu cơ sở.

## 11. Một quy trình ra quyết định thực tế

Khi được giao “AOP đang làm chậm ứng dụng”, hãy trả lời theo thứ tự:

**(1) Advice nào có chức năng bắt buộc, advice nào chỉ phục vụ quan sát?** Không gộp audit bắt buộc với tracing tùy chọn trong cùng quyết định.

**(2) Bao nhiêu join point hiện đang đi qua cơ chế, bao nhiêu thật sự cần advice?** Đo tần suất theo phương thức/loại nghiệp vụ; tìm các nhóm lời gọi cực nóng nhưng không thuộc mục tiêu.

**(3) Có thể chuyển điều kiện từ runtime sang thiết lập tĩnh không?** Nếu được, cần biết chi phí startup/cache và ảnh hưởng đến hot path.

**(4) Có thể loại trừ cả đối tượng/loại join point khỏi việc instrument không?** Điều này khác với chỉ bỏ qua advice trong handler và phụ thuộc khả năng của cơ chế AOP.

**(5) Bảng bao phủ có còn đúng ở các đường khó không?** Kiểm thử self-invocation, override, lỗi, retry, concurrency và async khi liên quan.

**(6) Sau khi thu hẹp, còn điểm nghẽn nào đáng tối ưu vi mô?** Profile CPU, allocation, I/O, locks; không thay API hay tạo object pool dựa trên suy đoán.

Ví dụ: hệ thống có 1 triệu lần gọi `find`, 10 nghìn lần gọi `reserve` và audit chỉ cần ở `reserve`. Nếu audit đang gắn lên mọi phương thức, bước đầu tiên là xác lập policy của `reserve`, kiểm chứng các đường có thể cập nhật tồn kho, rồi thu hẹp điểm chặn. Sau đó mới xét handler/matcher còn phải làm việc trên `find` hay không, có nên đổi dạng instrument hay giảm payload audit. Trật tự này giúp tách khoản tiết kiệm vì **ít việc phải làm** khỏi khoản tiết kiệm vì **mỗi việc làm nhanh hơn**.

## 12. Câu hỏi tự kiểm tra

1. **Vì sao pointcut hẹp hơn chưa chắc giảm overhead proxy?** Bởi đối tượng vẫn có thể được bọc proxy và handler vẫn được gọi trên các phương thức không khớp; chỉ giảm số lần advice chạy.
2. **Khác nhau giữa điều kiện tĩnh và động?** Tĩnh có thể xác định từ kiểu/chữ ký/metadata; động phụ thuộc đối số hoặc trạng thái của lần gọi. Tĩnh thường có cơ hội chuẩn bị sớm hơn.
3. **Điều gì xảy ra nếu matcher mới đắt hơn advice được bỏ?** Tổng CPU có thể tăng; phải đo cost của chính matching trên tất cả ứng viên.
4. **Khi nào không được loại bỏ advice hoặc sampling?** Khi đó là nghĩa vụ chức năng hoặc chính sách, như kiểm tra quyền, audit bắt buộc, cleanup và xử lý ngoại lệ cần thiết.
5. **Lợi ích giảm 98% số lần advice có phải giảm 98% latency?** Không. Đó là giảm số lượt advice, trong khi tổng độ trễ còn gồm nghiệp vụ, proxy, matching, I/O và tải hệ thống.
6. **Vì sao phải xét self-invocation và retry?** Chúng làm thay đổi những điểm chặn được kích hoạt và số lần nghiệp vụ thực thi; có thể khiến policy bị bỏ sót hoặc audit bị nhân bản.
7. **Vì sao phải quan sát cả p99 và allocation?** Advice phụ có thể làm tăng GC/lock/queue dưới concurrency, gây chậm ở đuôi phân phối dù mức trung bình thấp.
8. **Nên bắt đầu tối ưu ở đâu khi một advice bị gọi quá nhiều?** Trước tiên xác định tập join point thật sự cần theo hợp đồng nghiệp vụ, kiểm chứng bao phủ rồi thu hẹp phạm vi hợp lệ; tiếp theo đo chi phí của phần còn lại.

**Kết luận thực hành:** Trong AOP, một pointcut đúng và phạm vi can thiệp có chủ đích thường quan trọng hơn việc làm cho một advice vốn không cần thiết chạy nhanh thêm vài phép tính. Chỉ thu hẹp phạm vi trong ranh giới chức năng cho phép, xác minh đường gọi thực tế, đo cả số lượt advice lẫn chi phí matching/dispatch còn lại, rồi mới đi vào tối ưu vi mô đã có bằng chứng.