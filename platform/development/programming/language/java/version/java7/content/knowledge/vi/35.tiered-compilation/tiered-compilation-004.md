# Inline, tối ưu theo hồ sơ và khả năng quay lại mã ít tối ưu của JIT phân tầng

## 1. Bài toán: tối ưu mạnh khi chương trình Java đang chạy

Trong HotSpot JVM hiện đại, bytecode của Java có thể được thực thi bằng **trình thông dịch (interpreter)** hoặc mã máy do **trình biên dịch Just-In-Time (JIT)** tạo ra. JVM không cần dịch toàn bộ ứng dụng sang mã máy được tối ưu tối đa ngay khi khởi động: nhiều phương thức chỉ chạy một vài lần, trong khi một số đường xử lý được gọi hàng triệu lần.

**Tiered compilation (biên dịch phân tầng)** kết hợp interpreter, trình biên dịch nhanh **C1** và trình biên dịch tối ưu sâu **C2**. HotSpot dùng dữ liệu ghi nhận khi chạy (*runtime profile*) để chọn:
- Khi nào phương thức hoặc vòng lặp đủ nóng (*hot*) để biên dịch.
- Nên biên dịch ở mức tối ưu nào.
- Nên **inline** lời gọi nào, đặc biệt lời gọi ảo hoặc qua interface.
- Có thể dự đoán nhánh, loại đối tượng hoặc trường hợp phổ biến nào để tối ưu mạnh hơn.
- Làm gì khi một giả định tối ưu không còn đúng: **deoptimization**, quay lại cách thực thi an toàn và có thể biên dịch lại.

Các khả năng này được giới thiệu từ nhiều phiên bản Java trước, trong đó có nền tảng tiered compilation từ Java 7, và **vẫn được sử dụng trong HotSpot JDK hiện đại (bao gồm Java 17, 21, 25 và 26)**. Bài này chỉ tập trung vào cơ chế còn có giá trị thực hành hiện nay.

**Kết quả học tập:** giải thích được inlining dựa trên profile, nhận ra vì sao tối ưu hóa có thể bị thu hồi, đọc log biên dịch cơ bản và tránh diễn giải sai số liệu benchmark.

## 2. Các tầng thực thi liên quan đến inlining và profile

HotSpot có những mức (level) thường được mô tả như sau:

| Level | Công cụ thực thi | Đặc điểm |
| --- | --- | --- |
| **0** | Interpreter | Thực thi bytecode; có thể thu thông tin về số lần gọi, nhánh và kiểu đối tượng |
| **1** | C1 | Biên dịch nhanh, không thu profile chi tiết |
| **2** | C1 | Biên dịch nhanh với profile hạn chế |
| **3** | C1 | Biên dịch nhanh và thu profile đầy đủ hơn để C2 sử dụng |
| **4** | C2 | Tối ưu mạnh dựa trên các thông tin runtime đã thu thập |

Đây là **các mức biên dịch của HotSpot**, không phải một yêu cầu rằng mọi phương thức đều phải đi tuần tự từ 0 qua 1, 2, 3 rồi đến 4. Chính sách thực tế tùy thuộc độ nóng, kích thước phương thức, hoạt động của hàng đợi compiler, tải hệ thống và JDK. Một đường đi phổ biến là:

```text
Bytecode Java
     │
     ▼
Interpreter (level 0) ── thu số lần gọi / loại đối tượng / nhánh
     │ đủ nóng
     ▼
C1 với profiling (thường level 3)
     │ tiếp tục thu profile khi chạy native code
     ▼
C2 (level 4) ── tối ưu dựa trên profile, có thể inline
     │
     ├── giả định vẫn đúng ──► tiếp tục chạy mã tối ưu
     │
     └── giả định sai ──────► fallback / deoptimization
                                      │
                           chạy an toàn, cập nhật profile,
                           có thể biên dịch lại
```

Mã máy do JIT sinh ra được lưu trong **code cache**, có chi phí cấp phát và quản lý riêng. Trong quá trình biên dịch bất đồng bộ, một luồng ứng dụng có thể vẫn tiếp tục chạy bản mã đang dùng. Việc biên dịch/biên dịch lại là **quyết định runtime của JVM**, không làm thay đổi Java source hoặc file `.class`.

### Hot method và hot loop là hai tình huống khác nhau

- **Hot method:** một phương thức được gọi đủ nhiều, JVM có thể biên dịch toàn phương thức.
- **Hot loop:** một vòng lặp được thực thi nhiều lần ngay cả khi phương thức bao ngoài được gọi ít lần. HotSpot có thể dùng **On-Stack Replacement (OSR)** để chuyển một khung thực thi đang ở trong vòng lặp sang mã đã biên dịch.

OSR là **chuyển sang mã tối ưu cho vòng lặp đang chạy**; nó khác deoptimization, vốn là việc rời khỏi mã được tối ưu vì JVM cần quay lại đường thực thi bảo đảm đúng semantics.

## 3. Inlining là gì và tại sao quan trọng?

**Method inlining** là việc compiler đưa phần logic của phương thức được gọi vào ngay điểm gọi (*call site*) trong mã máy được tối ưu, nếu thấy có lợi và an toàn.

Giả sử có:

```java
static int plusFive(int x) {
    return x + 5;
}

static int process(int x) {
    return plusFive(x) * 2;
}
```

Về mặt ý tưởng, compiler **có thể** tạo chuỗi phép toán tương đương:

```text
process(x) ≈ (x + 5) * 2
```

Thay vì cần một lời gọi hàm riêng, compiler có cơ hội:
1. Loại bỏ chi phí gọi/trả về khi phù hợp.
2. **Truyền hằng số, tối ưu nhánh, loại phép toán dư thừa** xuyên qua ranh giới hai method.
3. Nhìn rộng hơn để áp dụng **escape analysis, scalar replacement** hoặc tối ưu vòng lặp khi điều kiện cho phép.

Cú pháp Java của chương trình **không bị chèn mã hay chỉnh sửa**. `inline` là quyết định của JIT khi tạo một phiên bản mã máy cụ thể, và việc quyết định có thể khác ở những lần biên dịch hoặc call site khác.

### Inline không được bảo đảm chỉ vì method nhỏ

HotSpot cân nhắc kích thước bytecode của callee, độ nóng tại call site, cấu trúc lời gọi, chi phí dự kiến, giới hạn độ sâu inlining, profile kiểu và ngân sách tạo mã máy. Một phương thức nhỏ có thể không được inline; một phương thức tương đối dài nhưng rất nóng đôi khi vẫn được inline theo chính sách và tình huống.

Các từ khóa Java cũng **không phải lệnh bắt buộc JIT inline**:
- `final` ở class hoặc method có thể giúp suy luận rằng không có override hợp lệ, nhưng không ép JIT inline.
- `static` giúp biết đích lời gọi rõ hơn, nhưng vẫn phải xét lợi ích/chi phí.
- Lời gọi qua **interface** hoặc phương thức virtual vẫn có thể inline nếu profile tại call site đủ hữu ích.

**Đánh đổi:** inline nhiều làm mã máy lớn hơn, tăng thời gian biên dịch hoặc áp lực code cache / instruction cache. Mục tiêu của HotSpot là tăng hiệu năng **tổng thể**, không phải inline mọi lời gọi.

## 4. Profile-driven optimization: học từ dữ liệu chạy thật

Profile (*hồ sơ runtime*) là tập quan sát của HotSpot, chẳng hạn:
- **Invocation count**: số lần phương thức được gọi.
- **Backedge count**: số vòng lặp/lần đi qua cạnh quay của vòng lặp, giúp nhận diện hot loops.
- **Receiver type profile**: ở một call site qua interface/virtual, kiểu lớp cụ thể của đối tượng nhận thường là gì.
- **Branch profile**: một nhánh `if/else` thường rẽ hướng nào.
- Một số thông tin về `null`, kiểu dữ liệu và trường hợp ít xuất hiện.

Đây là **dữ liệu thống kê theo những gì đã xảy ra** trong lúc JVM quan sát; nó không chứng minh rằng một tình huống chưa quan sát sẽ không bao giờ xuất hiện về sau.

### Monomorphic, bimorphic, polymorphic / megamorphic

Xét giao diện:

```java
interface PriceRule {
    int apply(int price);
}
```

Với lời gọi `rule.apply(price)`, HotSpot có thể quan sát:
- **Monomorphic:** call site chủ yếu hoặc chỉ thấy một lớp nhận, ví dụ `AddFive`.
- **Bimorphic:** thường thấy hai lớp nhận; đôi khi vẫn có thể inline hai đường kèm type checks.
- **Polymorphic/megamorphic:** thấy nhiều kiểu khác nhau, lời gọi khó tối ưu bằng một đích cụ thể; compiler có thể giữ dispatch động hoặc chỉ tối ưu một phần.

Không có ngưỡng số lượng kiểu tuyệt đối áp dụng như nhau cho mọi JVM/JDK. Quan trọng là **phân phối kiểu thực tế tại đúng call site**, không chỉ tổng số class implement interface trong toàn chương trình.

Ví dụ một dịch vụ thanh toán có nhiều implementation nhưng trong suốt giai đoạn warm-up chỉ dùng `CardPayment`. C2 có thể đưa `CardPayment.pay(...)` vào mã máy của caller và tối ưu các nhánh quen thuộc. Khi một yêu cầu mới chuyển qua `QrPayment`, chương trình **vẫn phải gọi đúng** implementation mới. Đây là lý do tối ưu dựa trên profile cần có cơ chế bảo vệ giả định.

## 5. Tối ưu mang tính phỏng đoán (speculative optimization)

JIT tối ưu dựa trên một số sự thật chắc chắn ở cấp Java và **một số giả định runtime có khả năng đúng cao**.

Giả sử tại một call site, 100% lần quan sát trước đó dùng `AddFive`. Một bản mã máy được tối ưu có thể có logic khái niệm sau:

```text
receive PriceRule rule
      │
      ▼
rule có kiểu AddFive?
   ├─ Đúng ─► dùng mã AddFive.apply đã inline và tối ưu
   │
   └─ Sai ──► đường dự phòng an toàn / uncommon trap
                 │
                 ├─ thực thi đúng lời gọi dynamic theo cơ chế phù hợp
                 └─ có thể deopt, thu profile mới và biên dịch lại
```

**Đây là sơ đồ cơ chế, không phải mã máy chắc chắn xuất hiện trong mọi lần chạy.** Một optimized compilation có thể chứa **type guard**, phụ thuộc vào cấu trúc class đã nạp (*class hierarchy dependency*) hoặc cơ chế fallback khác. Không phải mọi lần xuất hiện kiểu mới đều nhất thiết gây deoptimization; compiler có thể đã giữ sẵn đường dispatch tổng quát.

Tương tự, C2 có thể tối ưu một nhánh hiếm, giả định một giá trị thường khác `null` hoặc dùng profile để mở rộng vòng lặp. Khi giả định không phù hợp, JVM phải bảo toàn đầy đủ ý nghĩa của Java: null check, phép toán, ngoại lệ, lời gọi virtual, truy cập bộ nhớ và kết quả đều phải đúng.

### Deoptimization: quay lại đường thực thi an toàn

**Deoptimization (deopt)** là quá trình HotSpot rời khỏi một phiên bản mã đã được tối ưu khi những điều kiện hỗ trợ tối ưu hóa không còn phù hợp. Ví dụ: type guard thất bại, một đường nhánh trước đây hiếm nay xuất hiện, hoặc lớp mới được nạp làm mất hiệu lực suy luận về hierarchy.

Ở mức khái niệm:
1. Đoạn mã tối ưu gặp điều kiện cần fallback (*uncommon trap*) hoặc một sự kiện làm bản mã không còn hợp lệ.
2. JVM sử dụng metadata của compiled code để **khôi phục trạng thái thực thi logic**: các Java frame, local variables, operand stack; kể cả trạng thái của các method đã được inline khi cần.
3. Tiếp tục chạy bằng interpreter hoặc đường thực thi ít tối ưu hơn theo cơ chế thích hợp, **không làm mất kết quả hoặc bỏ qua quy tắc của Java**.
4. Profile được điều chỉnh theo trường hợp mới; JVM có thể **recompile** với giả định khác, hoặc tránh một tối ưu từng thất bại nhiều lần.

Deopt là **một cơ chế bình thường của JIT thích nghi**, không tự động đồng nghĩa với lỗi ứng dụng. Tuy nhiên, deopt quá thường xuyên tại một đường nóng có thể tốn CPU, tăng độ trễ và làm các bản mã được tối ưu thường xuyên mất hiệu lực.

### So sánh deopt, recompile và OSR

| Thuật ngữ | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| **Deoptimization** | Rời bản mã tối ưu khi không thể tiếp tục theo giả định cũ | Không phải Java exception |
| **Recompilation** | Biên dịch lại method ở level/chiến lược khác để phù hợp profile mới | Có thể diễn ra mà không có một deopt bất thường |
| **OSR** | Chuyển một vòng lặp đang chạy sang bản compiled code tại bytecode index thích hợp | Là cơ chế đi **vào** compiled code của vòng lặp, không phải tên khác của deopt |
| **Made not entrant** | Bản compiled method không còn được chọn cho các lần gọi mới | Có thể do thay bản biên dịch ở level cao hơn hoặc invalidation; bản thân dòng log này chưa chứng minh có deopt |

## 6. Ví dụ hoàn chỉnh Java 17+: call site nóng rồi xuất hiện kiểu mới

Ví dụ sau tạo một call site qua interface. Giai đoạn đầu chỉ gọi `AddFive` 500.000 lần; sau warm-up, có một lần gọi tới `DoublePrice`. Chương trình giúp hiểu **profile type đơn hình có thể phát sinh** và kiểm tra Java luôn gọi đúng implementation.

Tạo tệp **`TieredJitDemo.java`** bằng UTF-8:

```java
public class TieredJitDemo {
    interface PriceRule {
        int apply(int price);
    }

    static final class AddFive implements PriceRule {
        @Override
        public int apply(int price) {
            return price + 5;
        }
    }

    static final class DoublePrice implements PriceRule {
        @Override
        public int apply(int price) {
            return price * 2;
        }
    }

    static int calculate(PriceRule rule, int price) {
        return rule.apply(price) + 1;
    }

    public static void main(String[] args) {
        PriceRule commonRule = new AddFive();
        long total = 0;
        for (int i = 0; i < 500_000; i++) {
            total += calculate(commonRule, i % 10);
        }

        PriceRule newRule = new DoublePrice();
        System.out.println("Warm-up sum: " + total);
        System.out.println("Common rule: " + calculate(commonRule, 7));
        System.out.println("New rule: " + calculate(newRule, 7));
    }
}
```

Biên dịch và chạy trên HotSpot JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 TieredJitDemo.java
java TieredJitDemo
```

**Stdout chính xác** (không bật log compiler):

```text
Warm-up sum: 5250000
Common rule: 13
New rule: 15
```

Giải thích kết quả:
- `calculate(rule, x)` gọi `rule.apply(x)`, sau đó cộng thêm 1.
- Khi dùng `AddFive`, kết quả là `x + 6`. Các giá trị `i % 10` từ 0 đến 9 lặp đúng **50.000 vòng**, nên tổng là `(6 + 7 + ... + 15) × 50.000 = 5.250.000`.
- `calculate(commonRule, 7)` cho `7 + 5 + 1 = 13`.
- `calculate(newRule, 7)` cho `7 × 2 + 1 = 15`, chứng minh semantics động được giữ ngay cả khi call site trước đó chủ yếu thấy một kiểu.

**Giới hạn chứng minh:** một kết quả stdout đúng chỉ chứng minh **logic Java**, không chứng minh C2 đã inline hoặc đã deopt. JVM có thể thay đổi quyết định biên dịch theo kiến trúc CPU, bản JDK, độ nóng và tải máy. Muốn tìm bằng chứng về inlining, bật log chẩn đoán như phần tiếp theo.

## 7. Quan sát inlining và các level biên dịch

HotSpot hỗ trợ các cờ chẩn đoán hữu ích để học cơ chế, không cần gắn thư viện vào mã nguồn:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining TieredJitDemo
```

- `-XX:+PrintCompilation` in các nhiệm vụ biên dịch JIT, tên method, một số trạng thái và level.
- `-XX:+UnlockDiagnosticVMOptions` cho phép bật cờ chẩn đoán theo quy tắc HotSpot.
- `-XX:+PrintInlining` in quyết định inline hoặc lý do từ chối tại những call site được compiler xem xét.

Ví dụ các **mẫu cần tìm trong log** (là ký hiệu minh họa, không phải stdout cố định):

```text
... 3 ... TieredJitDemo::calculate (...)
  @ 2 TieredJitDemo$AddFive::apply (...) inline
... 4 ... TieredJitDemo::calculate (...)
  @ 2 TieredJitDemo$AddFive::apply (...) inline (hot)
  \-> TypeProfile (... counts) = TieredJitDemo$AddFive
```

Một lần chạy thực tế với HotSpot JDK 24 đã xuất hiện mẫu `calculate` được biên dịch ở level 3 rồi level 4 và inlining `AddFive.apply`, kèm `TypeProfile` của `AddFive`. **Con số thời gian, compilation id, số lần gọi và chính thứ tự dòng log không ổn định**; không kiểm tra bằng cách yêu cầu khớp nguyên văn toàn bộ log.

Các điểm giải mã cơ bản:
- `3`, `4` trong cột level thường là C1 profiling và C2 tối ưu; nhìn **đúng tiêu đề/cột của dòng compilation** vì các số khác cũng xuất hiện.
- `@ 2 ... inline`: method được xem xét/đưa vào tại **bytecode index** của call site tương ứng.
- `inline (hot)`: một quyết định inlining được compiler ghi nhận cho đường gọi nóng.
- `TypeProfile`: profile thống kê receiver type mà compiler sử dụng cho call site.
- Ký hiệu `%` trong output `PrintCompilation` thường đánh dấu một **OSR compilation**, không phải deopt.
- `made not entrant` nói rằng compiled method cũ không dùng cho **new invocations**; nó có thể xuất hiện khi một bản biên dịch khác thay thế bản trước. **Không kết luận “đã deopt” chỉ từ dòng này**.

**Lưu ý quan sát:** `-XX:+PrintInlining` tạo output lớn; lưu vào file, lọc theo `TieredJitDemo` và tên method quan tâm nếu ứng dụng lớn. Tác dụng và định dạng chi tiết các cờ `-XX` phụ thuộc HotSpot/JDK. Các cờ chẩn đoán làm tăng overhead và không nên bật thường xuyên trên hệ thống production.

### Khi nào được kết luận đã deoptimization?

Để khẳng định một lần deopt, cần bằng chứng **trực tiếp** từ sự kiện JVM/diagnostic phù hợp và tương quan với method, thời điểm, lý do; các log PrintCompilation/PrintInlining cơ bản không cung cấp đầy đủ chứng cứ cho mọi deopt.

Nếu chương trình chạy nhanh rồi kết thúc, optimizer có thể chưa có thời gian hoàn tất hoặc không chọn đường biên dịch bạn kỳ vọng. Một kiểu mới ở lần gọi cuối cũng **không bảo đảm** sẽ làm phát sinh deopt, vì code đã biên dịch có thể giữ đường fallback tổng quát.

Trong phân tích production, xem **JDK Flight Recorder (JFR)** và profiler chuyên dụng cùng dữ liệu latency/throughput; dùng bản ghi compiler khi cần hiểu inlining của một method cụ thể.

## 8. Ví dụ diễn tiến: profile đổi theo workload

Hình dung một phương thức xử lý nghiệp vụ:

```java
int evaluate(PriceRule rule, int price) {
    return rule.apply(price) + 1;
}
```

Theo thời gian:

| Giai đoạn | Quan sát tại runtime | JVM có thể làm gì? | Điều không được suy luận |
| --- | --- | --- | --- |
| Khởi động | Method chưa nóng | Interpret, thu số lần gọi | Không phải mọi method đều được C2 biên dịch ngay |
| Warm-up | 99% request dùng `AddFive` | C1 profiling; C2 có thể inline đường phổ biến | Không có bảo đảm inline dù profile rất lệch |
| Tối ưu ổn định | Kiểu receiver ít thay đổi | Chạy bản mã tối ưu hiệu quả | Không có nghĩa code đã bỏ kiểm tra semantics cần thiết |
| Workload chuyển đổi | Nhiều request bắt đầu dùng `DoublePrice` | Guard/fallback hoặc deopt; thu profile lại | Kiểu mới không bắt buộc tạo deopt |
| Sau thích nghi | Hai kiểu đều thường gặp | Có thể biên dịch lại code hỗ trợ nhiều kiểu hoặc dispatch tổng quát | Không bảo đảm sẽ có một bản C2 mới đúng một thời điểm cụ thể |

**Hệ quả thiết kế:** thời gian warm-up, loại dữ liệu đầu vào và tỷ lệ nhánh trong benchmark có thể ảnh hưởng mạnh đến JIT decisions. Chạy thử toàn `AddFive` rồi lấy kết quả suy luận cho ứng dụng có hàng chục implementation là sai ngữ cảnh.

## 9. Cân bằng hiệu năng: khi nào inlining giúp và khi nào gây chi phí?

Inlining thường có lợi khi:
- Callee nhỏ và được gọi rất thường xuyên tại một call site nóng.
- Type profile ổn định, giúp virtual/interface call được đặc thù hóa.
- Các phép tính sau inline cho phép constant propagation, branch elimination, loop optimization hoặc escape analysis.

Chi phí và giới hạn:
- **Code growth:** nhiều bản call site được inline có thể làm code cache lớn, tăng áp lực instruction cache.
- **Compiler CPU:** tối ưu sâu tốn thời gian biên dịch, có thể ảnh hưởng latency giai đoạn startup.
- **Profile churn:** input liên tục đổi kiểu/nhánh có thể gây nhiều lần invalidation, trap hoặc recompile.
- **Megamorphism:** nhiều kiểu receiver làm khó tối ưu một đích gọi phổ biến.
- **Đo sai:** tự viết một vòng lặp quá đơn giản có thể được constant-folding, dead-code elimination hoặc đo chủ yếu warm-up/compiler, không đo workload mong muốn.

### Thực hành đo hiệu năng đáng tin

1. **Đo đúng workload** gồm loại request và dữ liệu thực tế, có cả giai đoạn warm-up và steady-state.
2. **Theo dõi hiệu năng toàn hệ thống**, bao gồm p95/p99 latency, throughput, CPU, memory, GC, compilation activity.
3. Với microbenchmark, dùng **JMH** để kiểm soát warm-up, số iteration, fork và cách tiêu thụ kết quả; không dùng `System.nanoTime()` quanh một vòng lặp tự chế để kết luận một phương thức có inline.
4. Khi thấy thay đổi performance sau khi thêm implementation mới, kiểm tra độ đa hình tại **call site nóng** và quan sát compiler diagnostics trước khi sửa thiết kế.
5. Tránh ép hàng loạt `-XX:CompileCommand`, tắt tiered compilation hoặc dùng `-Xcomp`/`-Xint` như giải pháp tuning mặc định. Những chế độ này có giá trị chẩn đoán nhưng thay đổi đáng kể mô hình thực thi.

**Một lựa chọn thiết kế hợp lý** thường là viết Java dễ đọc, tạo ranh giới method rõ nghĩa và để HotSpot tự inline khi có lợi. Việc cố ép gộp tất cả code vào một method lớn có thể làm khó tối ưu và giảm khả năng bảo trì.

## 10. Những hiểu lầm cần tránh

| Khẳng định sai | Cách hiểu đúng |
| --- | --- |
| “`final` nghĩa là method chắc chắn được inline.” | `final` giúp ràng buộc override; inline còn phụ thuộc compiler, độ nóng, kích thước, call site và ngân sách tối ưu |
| “Chỉ `static` mới inline được.” | Interface/virtual calls cũng có thể inline theo profile và kiểm tra type |
| “C1 chỉ dùng trong Java cũ.” | C1 vẫn có vai trò quan trọng khi tiered JIT chạy trên HotSpot hiện đại |
| “Profile nói kiểu A 100%, vậy kiểu B không bao giờ xuất hiện.” | Profile phản ánh giai đoạn quan sát; workload/class loading có thể thay đổi |
| “JIT đoán sai thì Java trả kết quả sai.” | HotSpot dùng guard, fallback và deoptimization để bảo toàn semantics |
| “`made not entrant` luôn là lỗi hay deopt.” | Đó là trạng thái compiled code; cũng có thể do bản C2 thay bản C1 |
| “OSR giống deopt.” | OSR đi vào compiled code của vòng lặp; deopt rời optimized code khi cần |
| “Gọi nhiều lần chắc chắn C2 tối ưu ở level 4.” | Compile policy và JVM resource làm quyết định có thể khác |
| “Inlined method biến mất khỏi Java stack trace mãi mãi.” | JVM có metadata để khôi phục frame logic khi cần; stack trace/diagnostics không được hiểu chỉ theo số frame native |
| “Bật PrintInlining là benchmark hiệu năng.” | Diagnostic log giúp hiểu quyết định compiler, không thay đo latency/throughput có kiểm soát |

## 11. Tự kiểm tra kiến thức

1. Vì sao HotSpot dùng interpreter/C1/C2 thay vì biên dịch mọi method tối đa lúc khởi động?
2. Tại một call site `rule.apply(...)`, thông tin receiver type giúp compiler chọn phương án inline như thế nào?
3. Tại sao `final` không đủ để khẳng định một method chắc chắn được inline?
4. **Speculative optimization** khác tối ưu dựa trên quy tắc chắc chắn của ngôn ngữ ở điểm nào?
5. Khi giả định type/branch không còn đúng, **deoptimization** giữ nguyên hành vi Java bằng cách nào?
6. Tại sao một dòng `made not entrant` không đủ để chứng minh deopt?
7. Phân biệt deopt với OSR trong một vòng lặp đang chạy.
8. Vì sao kết quả stdout của `TieredJitDemo` là xác định nhưng compiler log có thể khác nhau giữa hai máy?
9. Khi workload từ một implementation thành nhiều implementation, những loại profile/latency/CPU nào cần xem trước khi chỉnh code?

**Điểm cần ghi nhớ:** Inlining là tối ưu tại **call site**, thường được dẫn dắt bởi **profile runtime**. HotSpot có thể phỏng đoán trường hợp phổ biến để tạo mã nhanh, nhưng phải bảo toàn semantics bằng **guard, fallback hoặc deoptimization** khi điều kiện thay đổi. Tiered compilation cho phép JVM liên tục cân bằng chi phí biên dịch với hiệu năng lúc chạy.

### Tài liệu chính thức và kỹ thuật còn phù hợp

- [Oracle Java SE 26 — Java HotSpot Virtual Machine Performance Enhancements (Tiered Compilation)](https://docs.oracle.com/en/java/javase/26/vm/java-hotspot-virtual-machine-performance-enhancements.html)
- [Oracle Java SE 26 — Compiler Control](https://docs.oracle.com/en/java/javase/26/vm/compiler-control1.html)
- [Microsoft for Java Developers — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/)
- [OpenJDK — JDK HotSpot compilation policy source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp)
