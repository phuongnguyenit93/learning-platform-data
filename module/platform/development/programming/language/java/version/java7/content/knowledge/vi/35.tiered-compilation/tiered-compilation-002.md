# Vai trò của các tầng biên dịch trong HotSpot

**Biên dịch phân tầng (*tiered compilation*)** là cơ chế tối ưu thực thi đang được sử dụng trong HotSpot JVM hiện đại. Java được biên dịch thành **bytecode** trong file `.class`; lúc chạy, HotSpot có thể thực thi bytecode bằng **trình thông dịch (*interpreter*)** hoặc biên dịch những đoạn code được dùng nhiều thành **mã máy (*native code*)** bằng bộ biên dịch tức thời (**JIT**, *Just-In-Time*). Việc áp dụng nhiều tầng giúp JVM cân bằng **khởi động nhanh**, **chi phí thu thập thông tin hành vi**, **thời gian CPU dành cho biên dịch** và **hiệu năng khi ứng dụng đã chạy nóng (*steady state*)**.

Đối với HotSpot phổ biến đi kèm OpenJDK/Oracle JDK hiện hành, có **hai bộ biên dịch JIT chính**: **C1** (biên dịch tương đối nhanh, hỗ trợ profiling) và **C2** (tốn công biên dịch hơn nhưng có nhiều tối ưu mạnh). JVM điều phối chúng bằng các **mức thực thi 0–4**. Mức 0 là thông dịch, mức 1–3 thuộc C1, mức 4 thuộc C2. Đây là **mức trong chính sách thực thi của HotSpot**, không phải phiên bản Java, không phải cấp ưu tiên thread và cũng không phải yêu cầu mỗi method bắt buộc đi qua mọi mức.

## 1. Bức tranh tổng thể

```text
                 Bytecode của một method
                           |
                           v
                [Level 0: Interpreter]
                   thu thập tín hiệu nóng
                     /             \
         C1 cần chạy nhanh          C1 cần thu thập profile
         ít/không profiling             |
                 |                  v
        [Level 1: C1]         [Level 2: C1 limited profile]
                              [Level 3: C1 full profile]
                                         |
                       thông tin kiểu/nhánh/tần suất đủ hữu ích
                                         v
                                  [Level 4: C2]
                              native code tối ưu mạnh

  Trong quá trình chạy, HotSpot có thể biên dịch lại, thay code,
  dùng OSR cho vòng lặp nóng hoặc deoptimize khi giả định thay đổi.
```

Mũi tên trên diễn tả **vai trò** chứ không phải chuỗi bắt buộc. Một tuyến phổ biến là `0 → 3 → 4`; có lúc JVM chọn `0 → 1` hoặc `0 → 2 → 3 → 4`, và nhiều method ngắn/hiếm dùng chỉ ở mức 0. Tài nguyên, hàng đợi biên dịch và dữ liệu thu thập được ảnh hưởng quyết định của HotSpot.

**Tại sao không dùng ngay C2 cho mọi method?** Biên dịch C2 cần CPU và thời gian. Một method chỉ được gọi vài lần có thể kết thúc nhiệm vụ trước khi chi phí biên dịch hoàn vốn. Ngược lại, một method được gọi hàng triệu lần có thể hưởng lợi lớn từ tối ưu chuyên sâu. Tầng C1 tạo mã máy nhanh hơn và có thể thu profile trong lúc chương trình tiếp tục xử lý.

## 2. Vai trò từng mức 0–4

| Mức thực thi | Thành phần thực thi | Vai trò nổi bật | Đánh đổi |
| --- | --- | --- | --- |
| **Level 0** | **Interpreter** | Thực thi bytecode ngay, không phải chờ biên dịch native; thu các thống kê cơ bản để phát hiện code nóng | Chi phí thông dịch mỗi lần chạy thường cao hơn native code đã JIT |
| **Level 1** | **C1 — không profiling** | Tạo native code tương đối nhanh, tối ưu trong phạm vi C1, tránh overhead thu profile bổ sung | Không tạo bộ thông tin phong phú để C2 tận dụng theo tuyến thông thường |
| **Level 2** | **C1 — limited profile** | Tạo native code và duy trì các bộ đếm như số lần gọi, *backedge* của vòng lặp | Có overhead đếm nhưng ít hơn level 3; không thu toàn bộ profile |
| **Level 3** | **C1 — full profile** | Vừa chạy native code vừa thu thông tin động chi tiết (ví dụ kiểu nhận ở call site, phân bố nhánh, theo cơ chế HotSpot) để hỗ trợ quyết định/tối ưu sau này | Code có instrumentation nên không nhất thiết nhanh bằng C1 level 1/2 cho mọi method |
| **Level 4** | **C2 — fully optimizing** | Dùng thông tin profile và phân tích tĩnh để xây dựng native code tối ưu sâu cho phần code có giá trị tối ưu | Biên dịch nặng hơn; có thể dựa trên giả định cần được kiểm tra và hoàn nguyên khi không còn đúng |

### Level 0: interpreter tạo điểm xuất phát linh hoạt

Interpreter đọc và thực thi bytecode theo ngữ nghĩa Java. Với một method chỉ gọi một lần, cách này giúp tránh công sức JIT không cần thiết. Trong quá trình chạy, HotSpot quan sát các dấu hiệu như **số lần method được gọi** và **số lần nhảy ngược của vòng lặp** (*backedge*); các thông tin này hỗ trợ xác định phần code nào đáng biên dịch.

Điều cần hiểu: interpreter **không phải một phiên bản bytecode lỗi thời**; đây là thành phần hiện hành trong mô hình thực thi HotSpot. Một số cơ chế JVM mới có thể bổ sung khả năng chuẩn bị hoặc nạp mã trước khi chạy, nhưng không làm mất vai trò của interpreter và các mức tiered trong quá trình JIT hoạt động.

### Level 1: C1 không thu profile

Level 1 thường được mô tả là **C1 with no profiling**. Nó tạo bản native code với tối ưu của C1 mà không thêm instrumentation để thu dữ liệu phục vụ tuyến C2 đầy đủ. Lợi ích chính là **biên dịch nhanh hơn C2** và thực thi nhanh hơn thông dịch trong nhiều trường hợp, với overhead profiling thấp.

Không nên hiểu chữ “fully optimized” trong thuật ngữ nội bộ của **C1 level 1** là mạnh tương đương **C2 level 4**: đó là mức tối ưu trong khả năng của **C1**. HotSpot có thể chọn level 1 cho các tuyến không cần/không có lợi từ full profiling hoặc khi cấu hình chỉ dùng các mức thấp.

### Level 2: C1 với thống kê hạn chế

Level 2 cung cấp **limited profiling**, điển hình là các bộ đếm invocation và backedge. Điều này cho phép JVM tiếp tục nhận biết method/loop nóng nhưng tránh một số chi phí instrumentation của level 3. Chính sách tiered có thể chọn level 2 khi trạng thái hàng đợi biên dịch hoặc tiến độ thu thập thông tin khiến level 3 chưa phải lựa chọn có lợi ngay.

Đây là **một mức chiến lược**, không phải “biên dịch lỗi”, “mức trung gian luôn bắt buộc”, hoặc chứng cứ JVM đang thiếu bộ biên dịch C2.

### Level 3: C1 thu profile phong phú

Level 3 tạo native code do **C1** sinh ra nhưng duy trì thông tin chạy thực tế phong phú hơn trong các cấu trúc profile của HotSpot như **MethodData (MDO)**. Tùy phương thức, dữ liệu có thể liên quan tới:

- **Invocation count / loop backedges:** method hoặc vòng lặp chạy thường xuyên tới mức nào;
- **Branch behavior:** nhánh nào thường xảy ra;
- **Receiver types:** các kiểu đối tượng thực tế tại lời gọi ảo, giúp dự đoán/inlining;
- **Những quan sát động khác** mà policy và bộ tối ưu có thể dùng.

Mục tiêu không chỉ là tăng tốc hiện tại; level 3 còn **tạo dữ liệu giúp level 4 tối ưu có cơ sở**. Việc thu profile có chi phí, nên nhiều code ở level 3 có thể không nhanh bằng bản C1 bỏ instrumentation. HotSpot đánh đổi một phần chi phí trước mắt để cải thiện chất lượng code tối ưu sau này.

### Level 4: C2 tối ưu sâu

C2 chịu trách nhiệm phần biên dịch **full optimization** trong HotSpot C1/C2 thông thường. Tùy code và dữ liệu quan sát, C2 có thể thực hiện:

- **Inlining:** đưa phần thân lời gọi phù hợp vào caller, mở ra cơ hội tối ưu xuyên phương thức;
- **Speculative optimization:** tối ưu dựa trên những kiểu/đường chạy thường gặp và đặt guard phù hợp;
- **Loop optimizations:** cải thiện vòng lặp khi phép biến đổi an toàn;
- **Escape analysis / scalar replacement:** loại bớt một số cấp phát đối tượng và truy cập trung gian khi phân tích chứng minh được;
- **Loại bỏ tính toán dư thừa** và tối ưu biểu diễn/phát mã máy.

Không phải mọi tối ưu này đều áp dụng cho mọi method. C2 phải giữ đúng ngữ nghĩa Java, giới hạn bởi kích thước code, CPU, profile và khả năng chứng minh. **Level 4 không phải lời hứa rằng mọi method đều đạt tốc độ tối đa**; một method ít được gọi có thể chưa từng đến đó.

## 3. JVM quyết định nâng tầng như thế nào?

### Phát hiện “hot code”

HotSpot không chỉ đếm số lần phương thức được gọi. **Backedge** là cạnh luồng điều khiển quay về phần trước của code, thường liên quan đến vòng lặp; một method chỉ được gọi một lần nhưng có loop chạy cực lâu cũng có thể đáng được JIT. Ngược lại, method gọi rất nhiều lần nhưng mỗi lần làm ít việc vẫn phải cân nhắc chi phí biên dịch.

Chính sách biên dịch tổng hợp:

1. **Số lần thực thi** method và vòng lặp;
2. **Tốc độ tăng** các bộ đếm (để phát hiện method còn đang nóng hay đã nguội);
3. **Tình trạng compile queue** của C1/C2 và tài nguyên CPU;
4. **Số liệu profile sẵn có**, kích thước method, tính đủ điều kiện biên dịch;
5. Các **heuristic** cụ thể của phiên bản HotSpot.

Vì vậy không nên giải thích tiered compilation bằng **một ngưỡng call count cố định** hoặc khẳng định “cứ 10.000 lần thì C2 biên dịch”. Ngưỡng và đường chuyển tầng được JVM điều chỉnh theo hoàn cảnh.

### Những tuyến chuyển tầng điển hình

```text
Tuyến thường gặp:          0 -> 3 -> 4
Tuyến ưu tiên C1:          0 -> 1
Tuyến giảm profiling:      0 -> 2 -> 3 -> 4
Method ít dùng:            0 -> (không nhất thiết JIT)
Khi giả định không còn đúng: 4 -> deoptimize -> tiếp tục ở mức thích hợp
```

Đây là những **khả năng**, không phải hợp đồng API. Có method chuyển cấp trực tiếp, method được biên dịch lại nhiều lần, hoặc mức JIT khác nhau tùy cấu hình JVM và thời điểm đo. Nếu xem log thấy level 4 xuất hiện mà không thấy level 2, đó là hành vi bình thường.

### Compiler threads và compile queues

C1 và C2 dùng công việc biên dịch trong các luồng JVM. Lời gọi tới một method nóng có thể tiếp tục thực thi phiên bản hiện có trong khi bản native mới đang được biên dịch. HotSpot không cần dừng toàn ứng dụng để “đợi C2 cho mọi method” mỗi khi code nóng.

Vì các biên dịch có **chi phí CPU và bộ nhớ**, hàng đợi lớn làm tăng thời gian đến bản code tối ưu. Trong giai đoạn khởi động của ứng dụng lớn, CPU có thể dùng nhiều cho C1/C2; throughput ban đầu khác với khi ứng dụng đã nóng. Khi đo hiệu năng, nên xem **warm-up** và **steady state** như hai trạng thái khác nhau.

## 4. OSR: tối ưu vòng lặp đang chạy

**On-Stack Replacement (OSR)** cho phép HotSpot chuyển một vòng lặp đang chạy trong một method sang bản code biên dịch phù hợp mà **không buộc phải chờ toàn bộ method kết thúc rồi gọi lại**.

Tình huống:

```java
static long countItems(long limit) {
    long total = 0L;
    for (long i = 0; i < limit; i++) {
        total += i;
    }
    return total;
}
```

Đây là **đoạn method minh họa**, chưa phải chương trình độc lập. Nếu gọi `countItems` một lần với `limit` rất lớn, interpreter có thể thấy backedge tăng nhanh và yêu cầu biên dịch một **OSR entry** cho vị trí vòng lặp thích hợp. Khi bản code sẵn sàng, JVM có thể chuyển trạng thái đang chạy sang mã máy được biên dịch.

Trong output `-XX:+PrintCompilation`, ký hiệu **`%`** thường báo một tác vụ biên dịch kiểu OSR; con số vị trí bytecode (BCI) có thể đi kèm. OSR khác với việc tạo compiled entry từ đầu method; một method có thể có cả bản OSR và bản non-OSR.

**Bài học:** “method gọi một lần” không đủ để kết luận “không thể JIT”. Cần xem cả số vòng lặp và sự kiện OSR.

## 5. Profiling, speculative optimization và deoptimization

Giả sử trong lúc warm-up, một điểm gọi phương thức ảo gần như luôn gặp instance cùng một lớp cụ thể. Profile từ tier thấp có thể giúp C2 **inline** đường gọi phổ biến, kèm điều kiện bảo vệ (*guard*) nếu tối ưu đó dựa vào giả định không luôn đúng.

Khi tải hoặc dữ liệu thay đổi, lớp nhận thực tế có thể khác. **Deoptimization** cho phép HotSpot rời phiên bản native code dựa vào giả định không còn phù hợp và khôi phục trạng thái thực thi cần thiết để chạy đúng ngữ nghĩa Java, thường về interpreter hoặc phiên bản code thích hợp. Sau đó JVM có thể thu dữ liệu và biên dịch lại.

Phân biệt:

- **Profile** là quan sát những hành vi đã xảy ra, không phải cam kết hành vi tương lai;
- **Speculative optimization** được bảo vệ để vẫn đảm bảo tính đúng đắn;
- **Deoptimization** là cơ chế bình thường của JIT động, không đồng nghĩa exception trong code nghiệp vụ;
- **Biên dịch lại/đổi cấp** có thể khiến cùng một method xuất hiện nhiều lần trong log.

Nếu profiling trong môi trường benchmark khác xa traffic thật, kết quả tối ưu và độ trễ thực tế cũng có thể khác. Vì thế benchmark Java cần thời gian warm-up phù hợp và workload đại diện, không chỉ chạy một lần rồi lấy thời gian.

## 6. Ví dụ Java 17+: quan sát các tầng qua `PrintCompilation`

Chương trình sau gọi một method tính tổng bình phương nhiều lần để tạo **hot method**. Kết quả tính toán có thể xác nhận độc lập với JVM; việc **method được biên dịch ở tier nào, lúc nào** là quyết định runtime và có thể khác nhau theo máy/JDK.

Tạo tệp **`TieredRolesDemo.java`**:

```java
public final class TieredRolesDemo {
    static int sumSquares(int limit) {
        int sum = 0;
        for (int i = 1; i <= limit; i++) {
            sum += i * i;
        }
        return sum;
    }

    public static void main(String[] args) {
        long checksum = 0L;

        for (int i = 0; i < 100_000; i++) {
            checksum += sumSquares(i % 20 + 1);
        }

        System.out.println("checksum=" + checksum);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TieredRolesDemo.java
java TieredRolesDemo
```

**Stdout của riêng chương trình**, khi chạy không bật log bổ sung:

```text
checksum=80850000
```

Lý do kết quả chính xác: `sumSquares(n)` tính `1² + 2² + ... + n²`. Trong 100.000 vòng lặp, các giá trị `1...20` mỗi giá trị xuất hiện 5.000 lần; tổng các tổng bình phương từ `n=1` đến `20` bằng `16170`, nên `16170 × 5000 = 80850000`. Kết quả này không phụ thuộc tier nào đang chạy vì JIT phải bảo toàn ngữ nghĩa Java.

### 6.1. Quan sát JIT biên dịch

```bash
java -XX:+PrintCompilation TieredRolesDemo
```

Lệnh in **sự kiện biên dịch của toàn JVM**, bao gồm code thư viện JDK và chương trình; dòng chương trình có thể xen với nhiều dòng log. Tìm chuỗi:

```text
TieredRolesDemo::sumSquares
TieredRolesDemo::main
```

Một dòng thường có cấu trúc khái quát:

```text
<time> <compile-id> [flags] <level> <class>::<method> (<bytecode-size> bytes)
```

Dòng trên là **sơ đồ cột**, không phải mẫu stdout bắt buộc của phiên bản JDK cụ thể. Nếu nhìn thấy số `3` cạnh tên method ở một dòng rồi `4` ở dòng khác, đó là dấu hiệu JVM đã biên dịch ở **C1 full profiling** rồi **C2 optimizing**. Nếu không thấy đủ hai mức trên một lần chạy, **không** kết luận JVM hoặc demo bị lỗi: chương trình ngắn, JIT dùng heuristic, có thể inline, dùng OSR hoặc chưa kịp in mọi compilation trước khi kết thúc.

Các dấu hiệu hữu ích:

- `%`: biên dịch **OSR** ở một vị trí vòng lặp;
- `made not entrant`: một bản compiled method không còn được dùng cho các lời gọi mới; có thể do đã có bản khác hoặc thay đổi giả định;
- `made zombie`: code đã không còn sử dụng và có thể được thu dọn theo cơ chế code cache;
- `n` hoặc các cờ khác: mô tả tính chất compilation như native wrapper; không phải tier.

### 6.2. Thử giới hạn C1 để thấy khác biệt

```bash
java -XX:TieredStopAtLevel=1 -XX:+PrintCompilation TieredRolesDemo
```

`-XX:TieredStopAtLevel=1` yêu cầu HotSpot **dừng tại level 1** trong cấu hình tiered này, vì thế bạn thường quan sát các compilation ở C1 level 1 thay vì C2 level 4. Đây là phép thử để hiểu vai trò các tầng; nó có thể làm giảm hiệu năng tải dài chạy nóng vì không cho phép phần tối ưu sâu của C2.

Để so sánh với chế độ interpreter:

```bash
java -Xint TieredRolesDemo
```

`-Xint` dùng interpreter để thực thi bytecode, không dùng JIT theo thông lệ. **Checksum vẫn phải là 80850000**; chỉ thời gian thực thi có thể khác. Không lấy một vòng chạy ngắn làm benchmark hoặc tự động kết luận C2 luôn nhanh hơn C1 trong mọi ca thử.

### 6.3. Xem JVM đang bật tiered compilation hay không

```bash
java -XX:+PrintFlagsFinal -version
```

Tìm hai biến **`TieredCompilation`** và **`TieredStopAtLevel`** trong output. Trên HotSpot Server thông dụng, tiered compilation thường đang bật, mức dừng tối đa có thể là `4`. Giá trị thực tế vẫn phụ thuộc **vendor, build, cách khởi chạy và cờ JVM**; vì thế kiểm tra đúng JVM mà ứng dụng sản xuất đang dùng.

Khi cần quan sát quyết định **inlining** trong phiên chẩn đoán chuyên sâu:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining TieredRolesDemo
```

`PrintInlining` tạo nhiều thông tin và có thể ảnh hưởng thời gian chạy khi ghi log. Nó giúp thấy điểm gọi nào được inline/bỏ qua, nhưng không phải bản kế hoạch tối ưu bất biến. Với chương trình nhỏ, inlining của `sumSquares` vào `main` có thể thay đổi việc các compilation xuất hiện trong log.

## 7. Code cache và chi phí tài nguyên của JIT

Native code do C1/C2 tạo ra nằm trong **code cache** của JVM. Tiered compilation có thể tạo nhiều bản mã của cùng một method trong các giai đoạn khác nhau; code cache phải được quản lý và tái sử dụng. Trong HotSpot hiện nay, **segmented code cache** tách những vùng chứa code có tính chất khác nhau, ví dụ bản profiled và bản không profiled.

Điều này dẫn tới hai nhận định thực tế:

1. **JIT không miễn phí**: tăng CPU cho compiler threads, bộ nhớ native/code cache, dữ liệu profile và thời gian warm-up. Không phải toàn bộ CPU cao khi khởi động đều do ứng dụng nghiệp vụ.
2. **Tiered mang lợi ích tổng thể**: có thể tránh phải trả ngay chi phí C2 cho mọi method, đồng thời tăng dần chất lượng native code ở những điểm nóng thật sự.

Code cache quá căng hoặc việc compilation bị vô hiệu hóa vì tài nguyên có thể ảnh hưởng hiệu năng. Khi đánh giá ứng dụng thật, cần quan sát CPU, thời gian startup, throughput, latency và bộ nhớ native cùng GC/heap metrics; GC log **không thay thế** log JIT.

## 8. Ý nghĩa với hiệu năng và cách vận dụng

### Startup, warm-up và steady state

- **Startup**: nhiều lớp được load, code nghiệp vụ lần đầu chạy; interpreter/C1 giúp ứng dụng tiến triển trong khi code nóng được nhận diện.
- **Warm-up**: HotSpot thu profile, thêm compilation vào queue, thay thế những bản code cũ bằng native code ở tier khác; CPU, latency và throughput có thể biến động.
- **Steady state**: một số method nóng có bản code C2 phù hợp; vẫn có thể xuất hiện compilation mới khi workload chuyển hướng, các lớp mới được nạp hoặc giả định trước đó không còn đúng.

Warm-up **không có độ dài cố định**, cũng không được xác định chỉ bằng số lần gọi main method. Nhiều ứng dụng server cần thử ở mức lưu lượng, tỷ lệ nhánh, kiểu request và dữ liệu tương tự production.

### Khi nào nên điều chỉnh các flag?

Với ứng dụng thông thường, **ưu tiên mặc định của HotSpot** và đo đạc trước. Các cờ như `-XX:TieredStopAtLevel=1`, `-XX:-TieredCompilation` hay `-Xint` hữu ích để **thí nghiệm có kiểm soát**, nhưng không nên bật tùy tiện trong production chỉ để thấy khởi động nhanh hơn hoặc log ít hơn.

Ví dụ một tác vụ chạy rất ngắn có thể chú trọng thời gian startup, còn một dịch vụ xử lý request hàng ngày chú trọng throughput và tail latency sau warm-up. Không có một tier duy nhất tối ưu cho mọi workload.

### C1 và C2 khác với `javac`

- `javac`: chuyển **mã nguồn Java sang bytecode** trước khi chạy.
- **Interpreter**: thực thi bytecode trong HotSpot.
- **C1/C2**: chuyển bytecode/mẫu code nóng thành native code **khi JVM đang chạy**, với khả năng dùng dữ liệu thực thi để tối ưu.
- **OSR**: sử dụng mã đã biên dịch giữa chừng cho một vòng lặp đang hoạt động.
- **Deoptimization**: trở lại phương thức thực thi an toàn hơn khi giả định tối ưu không còn đúng.

Những công đoạn này có vai trò khác nhau. Bật `javac -O` không thay thế cơ chế tiered JIT.

## 9. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “JVM phải chạy 0 → 1 → 2 → 3 → 4 cho mọi method.” | Chuyển tầng do policy quyết định; tuyến phổ biến `0 → 3 → 4`, nhiều method bỏ qua mức hoặc không JIT. |
| “Level 1 là C1 tối ưu hoàn toàn giống C2.” | Level 1 tối ưu trong khả năng C1, không thu profile; level 4 do C2 tối ưu sâu hơn. |
| “Level 3 luôn nhanh hơn level 2.” | Level 3 thu profile đầy đủ hơn nên có instrumentation; mục tiêu còn là cung cấp dữ liệu cho C2. |
| “Không nhìn thấy level 4 nghĩa là JIT không hoạt động.” | C1 cũng là JIT; compilation có thể xảy ra ở các mức thấp hoặc chưa có đủ công việc nóng. |
| “Một method chỉ được gọi một lần không thể biên dịch.” | Vòng lặp trong method có thể nóng nhờ backedge và dùng OSR. |
| “Tối ưu C2 phải giữ mãi.” | Guard và deoptimization cho phép JVM rút lại giả định khi dữ liệu thực tế thay đổi. |
| “`PrintCompilation` chỉ in code của ứng dụng.” | Log bao gồm compilation của thư viện và JVM; cần lọc theo tên lớp/method. |
| “Mức 4 chắc chắn là nhanh nhất trong mọi bài thử ngắn.” | Hiệu năng tổng còn gồm thời gian biên dịch, CPU contention, warm-up và code cụ thể. |
| “`-XX:TieredStopAtLevel=1` là cấu hình production nên bật.” | Đó là lựa chọn có tradeoff, nên thử có đo đạc; mất khả năng tối ưu C2 có thể ảnh hưởng throughput. |
| “GC pause và JIT compilation là cùng một việc.” | GC quản lý bộ nhớ đối tượng, JIT tối ưu thực thi bytecode; cần metrics/log riêng. |

## 10. Checklist để tự kiểm tra kiến thức

1. Giải thích được tại sao HotSpot có **interpreter**, **C1** và **C2** cùng tồn tại.
2. Xác định đúng vai trò **level 0** (thông dịch), **1** (C1 không profiling), **2** (C1 limited), **3** (C1 full), **4** (C2).
3. Giải thích được mục đích của **profile** về kiểu, nhánh, số lượt gọi, vòng lặp trong việc tạo code tối ưu.
4. Hiểu rằng tuyến `0 → 3 → 4` chỉ là phổ biến, **không có đường nâng tầng bắt buộc** cho mọi method.
5. Phân biệt **OSR** với biên dịch entry của method và hiểu vai trò backedge.
6. Hiểu **speculation/deoptimization** là cơ chế duy trì đúng ngữ nghĩa khi profile thay đổi.
7. Tự chạy `TieredRolesDemo.java` với `-XX:+PrintCompilation`, lọc tên method, giải thích các level có trong log thay vì đoán số ID hoặc duration.
8. Đối chiếu checksum **80850000** giữa mặc định, `-XX:TieredStopAtLevel=1` và `-Xint`; quan sát chênh lệch thời gian nhưng không dùng một mẫu nhỏ để kết luận hiệu năng production.
9. Khi cần tối ưu ứng dụng thật, đo **startup, thời gian warm-up, throughput, p95/p99 latency, CPU, code cache** rồi mới quyết định có điều chỉnh flag hay không.

## Kết luận

**Vai trò của các tầng biên dịch HotSpot là phân phối chi phí tối ưu cho đúng đoạn code, đúng thời điểm:** interpreter giúp chạy ngay; **C1 level 1–3** đưa code sang native nhanh và có thể thu profile ở độ sâu khác nhau; **C2 level 4** dùng dữ liệu đã quan sát để sinh mã tối ưu chuyên sâu. **OSR** xử lý vòng lặp đang nóng, **deoptimization** bảo vệ tính đúng đắn khi giả định thay đổi, còn compiler policy quyết định đường chuyển mức dựa trên tải và tài nguyên. Trong HotSpot hiện đại, hãy quan sát behavior thực bằng `-XX:+PrintCompilation` và benchmark có warm-up đại diện thay vì áp một quy tắc nâng tầng cứng.

## Tài liệu tham khảo

- [Oracle JDK 25 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html): khái niệm tiered compilation và code cache, mô tả cơ chế hiện hành của HotSpot.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+PrintCompilation`, `-XX:TieredStopAtLevel`, `-Xint` và các cờ JIT có liên quan.
- [Microsoft for Java Developers — How Tiered Compilation works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): bảng level 0–4 và giải thích ngưỡng/profile/transition theo OpenJDK.
- [OpenJDK — compilationPolicy.hpp (nguồn mã hiện hành)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): cách HotSpot điều phối compilation trong triển khai thực tế.
