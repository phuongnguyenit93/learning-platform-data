# Thông dịch, thu thập hồ sơ và biên dịch lúc chạy trong HotSpot JVM

## 1. Vì sao Java có cả thông dịch và biên dịch lúc chạy?

Một lớp Java thường được `javac` biên dịch từ mã nguồn `.java` thành **bytecode** trong tệp `.class`. Bytecode là chỉ dẫn cho JVM; nó chưa phải mã máy tối ưu riêng cho CPU đang chạy ứng dụng. Trong **HotSpot JVM**, các phương thức có thể bắt đầu thực thi qua **trình thông dịch** (*interpreter*), được JVM quan sát khi chạy, rồi được bộ biên dịch **JIT (Just-In-Time)** chuyển thành mã máy khi thấy có lợi.

Mục tiêu của cơ chế này không phải biên dịch mọi phương thức càng sớm càng tốt. JVM cần cân bằng:

- **Thời gian khởi động:** thông dịch có thể bắt đầu chạy sớm mà chưa trả giá biên dịch nhiều mã máy.
- **Chi phí biên dịch và quan sát:** JIT tiêu tốn CPU, bộ nhớ, hàng đợi compiler và không gian **code cache**.
- **Hiệu năng khi chạy lâu:** phương thức và vòng lặp được sử dụng nhiều có thể hưởng lợi từ tối ưu hóa dựa trên hành vi đã quan sát.
- **Tính đúng đắn:** dù thực thi bằng interpreter hay mã JIT, chương trình phải giữ ngữ nghĩa Java; khi một giả định tối ưu hóa không còn đúng, JVM có thể quay lại đường thực thi an toàn.

Phạm vi bài: cách **HotSpot** (JVM dùng trong nhiều bản OpenJDK phổ biến) thực hiện **thông dịch → profiling → biên dịch lúc chạy** dưới cơ chế **tiered compilation**. Chi tiết tier và các cờ chẩn đoán là đặc thù HotSpot, không nên mặc định áp dụng nguyên xi cho mọi JVM hoặc mọi bộ biên dịch thay thế. Kiến thức và API/công cụ trong bài vẫn đang được dùng trên **JDK 17+**; không sử dụng các cơ chế Java đã lỗi thời.

### Phân biệt các bước hay bị nhầm

| Bước | Thời điểm | Đầu vào → đầu ra | Vai trò |
| --- | --- | --- | --- |
| `javac` | Thường trước lúc chạy | Nguồn Java → bytecode `.class` | Kiểm tra và biên dịch source, không thay thế JIT của HotSpot |
| Nạp/xác minh lớp | Khi JVM cần lớp | Bytecode và metadata → lớp có thể thực thi | Kiểm tra hợp lệ và chuẩn bị kiểu, liên kết theo cơ chế của JVM |
| Interpreter | Trong lúc chạy | Bytecode → hành động runtime | Thực hiện phương thức khi chưa có phiên bản JIT phù hợp, có thể thu thập thông tin |
| JIT compiler | Trong lúc chạy | Bytecode + thông tin runtime → mã máy | Biên dịch một phần mã theo quyết định của chính sách JVM |
| Deoptimization | Trong lúc chạy, khi cần | Trạng thái tối ưu hóa → trạng thái thực thi hợp lệ khác | Phục hồi khi một giả định trong mã tối ưu không còn phù hợp |

**Không nên hiểu “Java là interpreted language” hoặc “Java được compile một lần rồi chạy máy” như mô tả đầy đủ.** Một JVM hiện đại có thể vừa thông dịch, vừa biên dịch nhiều phiên bản của cùng một phương thức, và thay đổi phiên bản theo hành vi ứng dụng.

## 2. Chu trình: thông dịch → ghi nhận profile → quyết định biên dịch → thực thi tối ưu

Một cách hình dung dòng đời của một phương thức thường được gọi:

```text
Mã nguồn Java --javac--> bytecode (.class)
                              |
                              v
                  JVM nạp/xác minh lớp
                              |
                              v
                Interpreter (level 0)
                   |  đếm số lần gọi
                   |  ghi nhận nhánh/kiểu,
                   |  vòng lặp khi phù hợp
                   v
                  Profiling data
                   |
                   v
           Chính sách tiered JIT
        /            |              \
       /             |               \
 C1 compile      Có thể tiếp tục     C2 compile
 nhanh           thông dịch          tối ưu sâu
       \             |               /
        \            v              /
         --> thực thi mã phù hợp <---
                    |
          profile thay đổi?
                    |
          +---------+---------+
          |                   |
         không                có
          |                   |
      chạy tiếp        có thể hủy mã
                     tối ưu (deopt),
                     quan sát/biên dịch lại
```

Đây là **sơ đồ logic**, không phải máy trạng thái bắt buộc: có phương thức được thông dịch suốt đời chương trình; có phương thức đi từ 0 → 3 → 4; có phương thức qua level 1 hoặc 2; cũng có phương thức được biên dịch lại hoặc có bản biên dịch riêng để tiếp tục vòng lặp đang chạy.

### Bước A — Thông dịch

Interpreter đọc bytecode và thực hiện phép toán, gọi phương thức, rẽ nhánh, truy cập đối tượng theo ngữ nghĩa JVM. Nó cung cấp đường bắt đầu nhanh cho mã mới được gọi. Tuy nhiên, mỗi lần thực hiện có overhead xử lý bytecode so với mã máy đã tối ưu, nhất là các đoạn nóng lặp lại nhiều lần.

Trong HotSpot, những bộ đếm và dữ liệu của phương thức được theo dõi dần khi mã chạy, kể cả trong interpreter khi cần. Không nên suy ra rằng một phương thức có vài lần gọi đã chắc chắn được JIT, hay rằng interpreter hoàn toàn không thu thập thông tin.

### Bước B — Thu thập hồ sơ thực thi (*runtime profiling*)

JVM thu thập **thông tin về hành vi thực tế** của mã nhằm quyết định việc biên dịch và tối ưu hóa. Các dạng thông tin hữu ích gồm:

- **Invocation count:** phương thức được gọi với tần suất nào.
- **Backedge/loop count:** các vòng lặp đã chạy lặp lại đến mức nào; một phương thức chỉ được gọi **một lần** vẫn có thể chứa vòng lặp rất nóng.
- **Nhánh điều kiện:** những nhánh thường được chọn, phục vụ bố trí và tối ưu đường chạy phổ biến.
- **Kiểu đối tượng/receiver type:** ở một lời gọi ảo, JVM có thể quan sát thường gặp một hay vài kiểu receiver nào; điều này có thể giúp **devirtualization**, **inlining** hoặc bỏ kiểm tra có điều kiện.
- **Một số thông tin runtime khác:** ví dụ trạng thái và đặc điểm của lời gọi, phạm vi kiểu, exception/khối mã, tùy vào phiên bản và tối ưu hóa cụ thể.

**Profile là dữ liệu quan sát, không phải hợp đồng nghiệp vụ.** Nếu 99,9% lần chạy đi nhánh A, JVM có thể tối ưu mạnh cho A nhưng **vẫn phải xử lý đúng nhánh B**. Tối ưu hóa nào phụ thuộc profile, CPU, bytecode, bộ biên dịch và heuristic; không bảo đảm JVM luôn ghi nhận hoặc dùng mọi chỉ số nêu trên.

### Bước C — Chính sách quyết định thời điểm và mức biên dịch

HotSpot không chỉ dựa vào một con số “gọi hơn N lần”. Chính sách biên dịch xem xét dữ liệu thực thi, loại phương thức, vòng lặp, hàng đợi C1/C2, tài nguyên máy, phiên bản JDK và cấu hình JVM. Nếu phương thức không đủ “nóng”, chi phí dịch mã có thể lớn hơn lợi ích nên JVM có thể giữ nguyên interpreter.

Quy trình có thể tạo **nhiều phiên bản biên dịch của một phương thức** theo từng level. Phiên bản đã cũ có thể chuyển thành *not entrant* hoặc được thu hồi khi không còn cần; không nên coi đó là lỗi ứng dụng.

## 3. Tiered Compilation của HotSpot: các level 0–4

HotSpot thường kết hợp trình thông dịch với hai compiler **C1** và **C2**. C1 biên dịch nhanh, phù hợp khi cần giảm thời gian warm-up; C2 dùng thời gian biên dịch nhiều hơn để tạo mã máy được tối ưu sâu cho đường chạy nóng.

| Level | Bộ thực thi | Profile trong giai đoạn đó | Ý nghĩa điển hình |
| --- | --- | --- | --- |
| **0** | Interpreter | Có thể tạo/duy trì profile và các bộ đếm | Khởi đầu thực thi bytecode; quan sát hành vi |
| **1** | C1 | Không thực hiện full profiling của level 3 | Mã máy C1 với độ trễ biên dịch thấp; hữu ích cho một số phương thức đơn giản hoặc cấu hình giới hạn tier |
| **2** | C1 | Profiling hạn chế, chủ yếu invocation/backedge counters | Một đường chạy trung gian khi cần giảm overhead profiling hoặc chờ compiler khác |
| **3** | C1 | Profiling đầy đủ hơn | Vừa chạy mã máy C1 vừa thu thập dữ liệu để tối ưu ở level cao |
| **4** | C2 | Dùng profile đã thu thập để tối ưu; bản mã này thường không tự duy trì full profiling kiểu level 3 | Tối ưu sâu cho những đoạn mã có lợi khi chạy lâu |

**Đường chuyển phổ biến là 0 → 3 → 4**, nhưng đây **không phải quy tắc tuyến tính**. Có thể đi qua 2, dừng ở 1/3, trực tiếp tới trạng thái biên dịch phù hợp hoặc tạo bản OSR. Tên và chính sách tier là **chi tiết của HotSpot hiện hành**, không phải một cấp trong Java Language Specification.

Ở nhiều bản HotSpot Server VM thông dụng, `TieredCompilation` được bật mặc định. Hãy kiểm tra VM **đang chạy của chính bạn** vì lựa chọn JVM, nền tảng, container, cờ launch và phân phối JDK có thể khác nhau:

```bash
java -XX:+PrintFlagsFinal -version
```

Trong kết quả, tìm `TieredCompilation` và `TieredStopAtLevel`. Một cấu hình HotSpot phổ biến có `TieredCompilation = true` và `TieredStopAtLevel = 4`; **đó không phải cam kết trên mọi JVM**. Nếu chỉ muốn quan sát bằng terminal, có thể lọc:

```bash
# Linux/macOS
java -XX:+PrintFlagsFinal -version | grep -E 'TieredCompilation|TieredStopAtLevel'

# Windows PowerShell
java -XX:+PrintFlagsFinal -version | Select-String 'TieredCompilation|TieredStopAtLevel'
```

Các cờ này chủ yếu phục vụ quan sát hoặc thí nghiệm có kiểm soát. Không thay đổi ngưỡng/tier trên production chỉ vì một ví dụ nhỏ chạy nhanh hơn.

## 4. C1 và C2 bổ sung nhau thế nào?

Tình huống: một phương thức xử lý request rất nhiều lần khi ứng dụng vừa khởi động.

- **Bước đầu:** interpreter chạy được ngay. Nó ghi nhận phương thức có được gọi liên tục không, vòng lặp dài không và một số dạng dữ liệu thực tế.
- **Giai đoạn nóng lên:** C1 có thể tạo mã máy nhanh. Ở level 3, mã C1 vẫn thu thập profile để làm đầu vào cho các tối ưu chuyên sâu về sau.
- **Giai đoạn chạy ổn định:** C2 có thể sinh mã máy chất lượng cao hơn theo dữ liệu thực tế: inlining một lời gọi thường gặp, loại bỏ một số phép kiểm tra dư khi chứng minh được, tối ưu vòng lặp, sắp xếp đường chạy phổ biến...
- **Khi workload đổi:** phiên bản C2 từng rất phù hợp có thể gặp kiểu dữ liệu hoặc tình huống chưa quan sát. HotSpot vẫn phải giữ semantics Java, nên có thể phải deopt hoặc tạo bản mã mới.

C1 **không đồng nghĩa với mã “sai” hay “chậm”**, và C2 **không bảo đảm mọi phương thức chạy nhanh hơn**. Phí biên dịch, kích thước mã, áp lực code cache và kích thước workload quyết định lợi ích ròng. Với chương trình ngắn, thời gian startup có thể quan trọng hơn throughput ổn định.

### Tại sao không biên dịch C2 cho tất cả ngay từ đầu?

- CPU dành cho compiler sẽ tranh chấp với CPU phục vụ ứng dụng.
- Chưa có profile thì C2 thiếu thông tin về kiểu hoặc nhánh thường xảy ra; mã tối ưu dựa trên giả định yếu có thể không hiệu quả.
- Những phương thức chỉ chạy vài lần hiếm khi hoàn vốn chi phí biên dịch.
- Mã native chiếm code cache; tài nguyên này có giới hạn và cần quản lý.
- Một số lời gọi nhỏ có thể được inline vào caller; quan sát một phương thức trong log phải xét cả việc mã của nó đã được đưa vào caller.

Cơ chế phân tầng giải quyết **bài toán kinh tế thực thi**: dành ít chi phí cho mã lạnh và đầu tư tối ưu sâu cho nơi có lợi ích đủ lớn.

## 5. Hot method và hot loop: invocation khác backedge

Hai dạng “nóng” cần phân biệt:

1. **Hot method:** một phương thức được gọi liên tục, ví dụ `parseItem()` chạy hàng triệu lần trong request processing.
2. **Hot loop:** một phương thức có thể chỉ được gọi vài lần nhưng chứa vòng lặp rất dài, ví dụ xử lý một tập dữ liệu lớn trong một lần gọi.

HotSpot theo dõi **invocation counter** và **backedge counter** để quyết định có cần biên dịch phương thức hay tạo bản chạy tối ưu ở một vị trí trong vòng lặp. Khái niệm *backedge* là đường điều khiển quay về phần lặp của bytecode.

### On-Stack Replacement (OSR)

Giả sử một phương thức đang chạy một vòng lặp hàng triệu lần **trên interpreter**. Nếu chờ phương thức trả về rồi mới dùng mã JIT ở lần gọi tiếp theo, ứng dụng có thể không bao giờ hưởng lợi trong vòng lặp hiện tại.

**OSR** cho phép HotSpot tạo một bản biên dịch có điểm vào tương ứng trạng thái **bên trong** phương thức/vòng lặp, rồi chuyển việc thực thi đang dở sang bản mã đó khi phù hợp. OSR không đồng nghĩa với “biên dịch lại toàn bộ ứng dụng”; nó là đường chuyển trạng thái runtime cho một đoạn mã đang hoạt động.

Trong log `-XX:+PrintCompilation`, dấu **`%`** thường chỉ tác vụ biên dịch **OSR**, và `@ <bci>` chỉ vị trí bytecode entry liên quan. Dấu cụ thể, thứ tự cột, số ID và khả năng nhìn thấy OSR có thể thay đổi theo JVM/JDK và workload.

**Lưu ý:** mã OSR không bắt buộc có hiệu năng giống chính phương thức đã được biên dịch ở entry thông thường. Khi đọc log cần phân biệt “biên dịch phương thức để gọi từ đầu” và “biên dịch để tiếp tục vòng lặp đang chạy”.

## 6. Tối ưu có giả định, deoptimization và biên dịch lại

Một ưu thế của JIT so với tối ưu chỉ dựa trên bytecode tĩnh là có thể tận dụng thông tin thực thi:

```java
interface Formatter {
    String format(String input);
}

final class UpperFormatter implements Formatter {
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}

static String render(Formatter formatter, String text) {
    return formatter.format(text);
}
```

Đây là **đoạn minh họa ý tưởng**, không phải một tệp `.java` độc lập. Nếu tại một call site, JVM chủ yếu quan sát `UpperFormatter`, C2 *có thể* dùng profile để tối ưu lời gọi interface thành đường thực thi nhanh, kèm điều kiện kiểm tra kiểu và đường dự phòng thích hợp. Nó không mặc định bỏ qua kiểu khác; Java vẫn phải xử lý đúng với bất kỳ `Formatter` hợp lệ nào.

Khi một kiểu mới xuất hiện, điều kiện tối ưu hóa có thể không thỏa. **Deoptimization** là cơ chế HotSpot dùng để rời khỏi mã máy mang giả định không còn hợp lệ và phục hồi trạng thái thực thi tương ứng (chẳng hạn interpreter), sau đó tiếp tục quan sát hoặc biên dịch lại khi cần. Đây là cơ chế bình thường của JVM, không phải bằng chứng ứng dụng sai hoặc JIT tạo kết quả không đáng tin.

- **Inlining:** thay lời gọi bằng thân phương thức khi có lợi; có thể dựa vào loại receiver và độ nóng.
- **Speculative optimization:** tối ưu theo điều kiện thường đúng nhưng vẫn giữ khả năng phục hồi khi điều kiện sai.
- **Deoptimization:** thoát khỏi bản mã tối ưu hoặc đánh dấu phiên bản không còn phù hợp.
- **Recompilation:** JVM có thể tạo mã khác sau khi thu thêm profile hoặc thấy workload đổi.

Một dòng `made not entrant` trong log biên dịch thường là dấu hiệu bản mã trước đó không còn là ứng viên vào mới; **không kết luận lỗi** chỉ từ dòng này. Deoptimization cũng có thể xảy ra vì thay đổi phụ thuộc lớp, giả định runtime hoặc các yếu tố khác ngoài việc dữ liệu đầu vào khác trước.

## 7. Ví dụ chạy được: một phương thức được gọi lặp lại

Đoạn sau tạo công việc thuần CPU có kết quả cố định. Nó giúp xem compiler hoạt động với một phương thức nhiều lần được gọi; chương trình **không cố bắt buộc một tier cụ thể**, vì chính sách JIT là động.

Lưu thành **`TieredJitDemo.java`**:

```java
public final class TieredJitDemo {
    static long compute(int x) {
        long acc = 0;
        for (int i = 0; i < 16; i++) {
            acc += (x * 31L + i * i) % 97;
        }
        return acc;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int i = 0; i < 1_000_000; i++) {
            checksum += compute(i & 255);
        }
        System.out.println("checksum=" + checksum);
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 TieredJitDemo.java
java TieredJitDemo
```

**Stdout chính xác khi chạy không kèm logging VM:**

```text
checksum=768050782
```

Giá trị được cộng vào `checksum` để chương trình có kết quả quan sát được. Hàm `compute` lặp 16 phép tính trên đầu vào `i & 255`, được gọi 1.000.000 lần; với HotSpot JIT bình thường nó là ứng viên đáng quan sát. Tuy nhiên, JIT có thể **inline**, biên dịch phương thức, tạo OSR hoặc tối ưu theo những cách khác; việc tên `compute` có xuất hiện trong log hay không và thứ tự tier là **không bảo đảm**.

Cùng mã nguồn có thể chạy với interpreter hoặc mã native được biên dịch, nhưng **kết quả tính toán Java phải như nhau**. Đây là ví dụ giải thích hành vi JIT, **không phải benchmark** hay chứng minh một biến thể JVM nhanh hơn.

### Chạy và quan sát hoạt động biên dịch

```bash
java -XX:+PrintCompilation TieredJitDemo
```

HotSpot in ra những thông tin về tác vụ biên dịch, có thể bao gồm thời điểm tương đối, compilation ID, level, tên class/phương thức, kích thước bytecode và trạng thái. Hãy **tìm `TieredJitDemo::compute` hoặc `TieredJitDemo::main`**, quan sát số level, và nếu có `%`/`@ ...` thì xem đó là thông tin OSR.

Log có thể chứa **hàng chục đến hàng trăm dòng cho lớp JDK**, compilation ID/timestamp/đường chuyển tier thay đổi giữa các lần chạy. **Không lấy log JIT làm stdout cố định** và đừng nhận định thất bại nếu chưa thấy level 4 trong một lần chạy ngắn.

Khi muốn xem quyết định inline chi tiết trong môi trường thử nghiệm:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining TieredJitDemo
```

`PrintInlining` có thể tạo lượng output lớn; chỉ bật khi cần chẩn đoán. Thông tin inline là quyết định của compiler tại bối cảnh cụ thể, không phải lời hứa mọi lần chạy đều như vậy.

### Chạy chế độ thông dịch để đối chiếu ngữ nghĩa

```bash
java -Xint TieredJitDemo
```

Stdout vẫn là:

```text
checksum=768050782
```

`-Xint` yêu cầu HotSpot dùng chế độ interpreted execution (ngoại trừ các cơ chế runtime/native đặc thù JVM) và không dùng JIT biên dịch bytecode Java theo lộ trình thông thường. Nó hữu ích để **hiểu/khắc phục lỗi** trong thử nghiệm, nhưng không phải cấu hình nên tự động áp dụng trên production.

Nếu muốn quan sát giới hạn tier C1 trong thí nghiệm riêng trên HotSpot:

```bash
java -XX:TieredStopAtLevel=1 -XX:+PrintCompilation TieredJitDemo
```

Điều này giới hạn level tối đa cho chính sách tiering của HotSpot được sử dụng, **không tương đương `-Xint`** và không chứng minh rằng level 1 sẽ tốt hơn trong hệ thống thật. `-XX:-TieredCompilation` cũng **không đồng nghĩa** tắt toàn bộ JIT; muốn chỉ thông dịch, dùng `-Xint`.

Không dùng `-Xcomp` như cách tạo benchmark thực tế: nó ép cách xử lý compilation khác với vận hành tự nhiên và có thể thay đổi đáng kể startup/warm-up.

## 8. Đọc log `PrintCompilation` và công cụ runtime

Đây là một minh họa **hình thức ý nghĩa** của output (không phải bản chép một lần chạy cụ thể):

```text
...  3  ... TieredJitDemo::compute (...)
...  4  ... TieredJitDemo::compute (...)
...  %  ... TieredJitDemo::main @ ... (...)
...      ... made not entrant ...
```

Cách đọc:

- **3 hoặc 4:** compiler level tương ứng của HotSpot (C1 với profiling ở 3, C2 ở 4).
- **`%`:** tác vụ OSR, thường kèm vị trí `@ ...` theo bytecode index.
- **`made not entrant`:** một bản mã không tiếp tục được dùng cho entry mới; có thể do thay thế/deoptimization, không tự suy ra lỗi.
- **Tên phương thức khác:** JIT còn biên dịch các phương thức của Java standard library và runtime, không chỉ mã của bạn.
- **Lệnh chạy ngắn:** việc không thấy đầy đủ các chuyển trạng thái không chứng minh tiered JIT bị vô hiệu hóa.

Lưu ý `PrintCompilation` là output chẩn đoán, có thể tăng chi phí logging, thay đổi timing và không được coi là API dữ liệu ổn định để xây parser phụ thuộc format.

### `jcmd`: xem trạng thái compiler của một JVM đang chạy

Trên một máy có JDK và quyền truy cập JVM phù hợp:

```bash
jcmd -l
jcmd <pid> Compiler.queue
jcmd <pid> Compiler.codelist
jcmd <pid> Compiler.codecache
```

`<pid>` là ID tiến trình cần xem, thay bằng số thật (ví dụ `12345`), không gõ nguyên dấu ngoặc nhọn; một số lệnh còn yêu cầu quy định về quyền truy cập/attach. `jcmd` xem tiến trình JVM **đang chạy**, không phải ứng dụng đã kết thúc.

- `Compiler.queue`: những phương thức còn chờ biên dịch tại thời điểm quan sát.
- `Compiler.codelist`: các phương thức đã biên dịch còn tồn tại trong code cache.
- `Compiler.codecache`: bố cục và vùng cache chứa mã native JIT.
- `VM.flags`: các cờ VM đang có hiệu lực, hữu ích để xác nhận cấu hình.

Nếu queue trống sau một lần gọi lệnh, điều đó có thể chỉ nghĩa là tại thời điểm đó không còn yêu cầu biên dịch nào đang chờ. Nếu code cache đã gần đầy, ứng dụng có thể bị ảnh hưởng throughput hoặc khả năng JIT tạo mã mới; nhưng cần đối chiếu workload, log và phép đo.

### Java Flight Recorder (JFR) để quan sát dài hạn

JFR là công cụ chẩn đoán hiện hành trong JDK. Có thể thu recording rồi kiểm tra thống kê/hồ sơ compiler thay vì phụ thuộc vào hàng nghìn dòng stdout:

```bash
java -XX:StartFlightRecording=filename=jit-demo.jfr,settings=profile,dumponexit=true TieredJitDemo
jfr summary jit-demo.jfr
jfr metadata --events jdk.Compilation
jfr print --events jdk.Compilation jit-demo.jfr
```

Số sự kiện thấy được phụ thuộc bản JDK, cấu hình sự kiện, thời gian chạy và workload; chương trình ví dụ có thể kết thúc quá nhanh để tạo recording phong phú. Trong ứng dụng chạy dài, có thể bắt đầu/điều khiển JFR bằng `jcmd ... JFR.start`, `JFR.dump` và `JFR.stop` khi phù hợp. Kiểm tra sự kiện hiện có bằng `jfr metadata` thay vì giả định mọi JVM ghi cùng bộ event.

JFR hữu ích khi cần tương quan thời điểm compilation với CPU, allocation, GC, thread activity và thời gian đáp ứng của ứng dụng. Bật JFR cũng có overhead; chọn cấu hình và phạm vi ghi có chủ đích.

## 9. Warm-up: vì sao hiệu năng đầu và cuối khác nhau?

Trong lần chạy đầu, HotSpot còn phải nạp lớp, khởi tạo class, diễn giải bytecode, ghi nhận profile và có thể compile mã. Sau một số lần lặp, mã hot có thể đã được tối ưu hoặc inline. Vì vậy:

- **Cold start** đo thời gian từ lúc process mới được tạo đến khi có thể làm việc; chịu ảnh hưởng class loading, bootstrap, I/O, GC và JIT.
- **Warm-up** là khoảng thời gian ứng dụng thay đổi trạng thái runtime (bao gồm JIT) khi tiếp nhận workload.
- **Steady state** là giai đoạn tương đối ổn định để đo throughput/latency, nhưng vẫn có thể có GC, deopt, thay đổi profile, biên dịch mới hoặc phụ thuộc tài nguyên hệ thống.
- **Tối ưu startup và tối ưu throughput** là hai mục tiêu khác nhau; có thể phải đánh đổi chi phí compilation ban đầu để đạt tốc độ lâu dài.

**Không dùng phép đo `System.nanoTime()` bao quanh một vòng lặp rất nhỏ làm kết luận hiệu năng JIT.** JVM có thể loại bỏ code không có tác dụng quan sát, inline, constant-fold, thay đổi profile theo lần chạy và GC chen ngang. Nếu thực sự muốn so sánh hiệu năng Java microbenchmark, dùng **JMH (Java Microbenchmark Harness)** với warm-up, fork, measurement iteration và tiêu thụ kết quả phù hợp. Với ứng dụng nghiệp vụ, đo trên workflow và dữ liệu gần production, cùng JDK/CPU/GC/cấu hình, rồi quan sát throughput, tail latency và CPU compiler.

Để tránh nhầm lẫn giữa JIT và lỗi thiết kế chương trình, hãy hỏi:

1. Ứng dụng thực sự chậm khi cold start hay chỉ sau khi chạy lâu?
2. Chỉ một phương thức bị nóng hay hiệu năng bị chi phối bởi I/O/khóa/GC?
3. CPU có đang bận với compiler thread trong warm-up không?
4. Code cache, compile queue và hoạt động deoptimization có dấu hiệu bất thường không?
5. Có workload đã đổi (kiểu dữ liệu, phân phối nhánh, lưu lượng, kích thước bộ dữ liệu) khiến profile cũ không đại diện nữa không?

Đừng kết luận “JIT chắc chắn chưa chạy” chỉ vì thời gian phản hồi chưa cải thiện; khi nút nghẽn là network hoặc database, biên dịch mã máy không thể sửa latency của hệ thống bên ngoài.

## 10. Những hiểu nhầm thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “`javac` đã biên dịch, vậy JVM không cần JIT” | `javac` tạo bytecode; HotSpot có thể biên dịch bytecode thành mã máy trong runtime |
| “Mọi phương thức đều phải qua 0 → 1 → 2 → 3 → 4” | Đường tier không tuyến tính bắt buộc; 0 → 3 → 4 là mẫu phổ biến, có nhiều ngoại lệ |
| “Method nào được gọi nhiều là tự động biên dịch đúng tại một ngưỡng cố định” | Heuristic còn xét loop/backedge, queue, độ nóng, cấu hình JVM và chi phí |
| “Chỉ method gọi nhiều mới nóng” | Một vòng lặp dài có thể được OSR dù method chỉ gọi ít lần |
| “C1 luôn chậm, C2 luôn nhanh” | C1 có chi phí compiler thấp; lợi ích tổng thể phụ thuộc startup, runtime, code cache và workload |
| “Profile là sự thật vĩnh viễn” | Profile phản ánh lịch sử quan sát; JIT vẫn phải giữ semantics với kiểu/nhánh mới |
| “Deoptimization chứng minh JVM sai” | Đây là cơ chế bình thường giúp phục hồi khi giả định tối ưu hóa không còn hiệu lực |
| “`-XX:-TieredCompilation` tương đương `-Xint`” | Vô hiệu tiering không đồng nghĩa vô hiệu mọi biên dịch JIT; `-Xint` mới dành cho chế độ interpreted |
| “Không thấy tên method trong log là method không chạy” | Method có thể chạy interpreted, được inline ở caller hoặc log ngắn không bao quát toàn bộ |
| “Dùng một vòng lặp và đồng hồ đủ để benchmark” | Cần kiểm soát warm-up, fork, loại dead-code elimination và nhiễu môi trường, thường dùng JMH |
| “Các cờ `-XX` là hợp đồng chuẩn Java” | Chúng thuộc implementation HotSpot, có thể đổi hoặc không tồn tại ở JVM khác |
| “Có JIT thì mọi ứng dụng tự nhanh hơn theo thời gian” | I/O, lock contention, GC, workload và các giới hạn khác vẫn có thể chi phối hiệu năng |

## 11. Tình huống áp dụng

### Tình huống A — Web service chậm vài giây sau deploy

Phân biệt startup framework/class loading/đọc cấu hình với việc JIT compile trong warm-up. Dùng quan sát thực tế: timeline CPU, JFR, compile activity, latency, GC. Không tăng ngưỡng/làm nóng bằng traffic giả trước khi hiểu chi phí và mục tiêu. Đối với ứng dụng có yêu cầu khởi động nhanh, cần tối ưu tổng luồng startup, không chỉ một flag JIT.

### Tình huống B — Batch chạy một vòng lặp khổng lồ duy nhất

Kiểm tra OSR. Method có thể chỉ được gọi một lần nhưng loop backedge tăng mạnh, giúp JVM quyết định JIT ngay trong lượt đang chạy. `PrintCompilation` có thể hiện dấu `%` của bản OSR; thiếu nó trong một lần chạy không đủ bằng chứng OSR không khả dụng.

### Tình huống C — Ứng dụng chạy lâu rồi bỗng giảm throughput

Kiểm tra workload có thay đổi không; đối chiếu deoptimization/recompilation với GC, network, database, code cache và contention. Một đợt recompilation ngắn có thể bình thường. Không tự ép bỏ C2 hoặc giảm tier chỉ từ một khoảng thời gian quan sát.

### Tình huống D — Muốn kiểm chứng JIT có bật không

Trên đúng VM, kiểm tra `PrintFlagsFinal` hoặc `jcmd <pid> VM.flags`; dùng `-XX:+PrintCompilation` trong môi trường thử nghiệm và đối chiếu với `-Xint`. Nếu chạy trên OpenJ9 hoặc JVM/bộ biên dịch khác, tra tài liệu của chính implementation, đừng dùng bảng level HotSpot như mặc định.

## 12. Tự kiểm tra kiến thức

1. Một method được gọi đúng **một lần** nhưng chứa vòng lặp 10 triệu lượt. Vì sao OSR vẫn có thể xảy ra?  
   **Trả lời:** JVM theo dõi backedge của vòng lặp; nếu hot, nó có thể biên dịch entry OSR và chuyển việc chạy dở từ interpreter sang mã máy.
2. Vì sao HotSpot cần C1 khi đã có C2?  
   **Trả lời:** C1 tạo mã nhanh và có thể hỗ trợ profiling ở các tier trung gian, giúp cân bằng chi phí warm-up với hiệu năng lâu dài.
3. Level 3 và level 4 khác nhau chính ở đâu?  
   **Trả lời:** level 3 dùng C1 với profiling đầy đủ hơn; level 4 là mã C2 tối ưu hóa dựa trên profile. Không phải mọi method đều nhất thiết đi qua cả hai.
4. JVM quan sát hầu hết receiver là kiểu A, sau đó gặp kiểu B. Kết quả Java có được phép sai không?  
   **Trả lời:** không. Guard/fallback hoặc deoptimization bảo đảm semantics; JVM có thể thu lại profile và biên dịch lại.
5. Thấy `made not entrant` trong `PrintCompilation` nghĩa là gì?  
   **Trả lời:** một bản mã được đánh dấu không còn dùng cho lời gọi mới; cần ngữ cảnh để hiểu, không mặc định là lỗi.
6. Tại sao checksum của `TieredJitDemo` không đổi khi chạy thường và `-Xint`?  
   **Trả lời:** interpreter và mã được JIT phải giữ cùng ngữ nghĩa Java; JIT chỉ được phép thay đổi cách thực thi và hiệu năng.
7. Vì sao không lấy một lần chạy `System.nanoTime()` để so sánh JIT/C1/C2?  
   **Trả lời:** compilation, inlining, GC, khởi tạo, optimization và scheduler tạo nhiễu; nên dùng thiết kế benchmark thích hợp (JMH) hoặc đo workload thật.

## 13. Tài liệu kiểm chứng hiện hành

- [OpenJDK — HotSpot Compilation Policy (mã nguồn hiện tại)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): mô tả level 0–4, counters, profile và cơ chế điều phối compilation.
- [OpenJDK Project Leyden — HotSpot Tiered Compilation primer](https://openjdk.org/projects/leyden/slides/leyden-jvmls-2023-08-08.pdf): giải thích các tier 0–4, profiling, speculation và deoptimization.
- [Microsoft for Java — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): minh họa chính sách tiering và các đường chuyển trạng thái.
- [Java SE 21 — `java` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xint`, `-XX:+PrintCompilation`, `-XX:+PrintInlining`, `-XX:-TieredCompilation` và các cờ JVM liên quan.
- [Java SE 21 — `jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Compiler.queue`, `Compiler.codelist`, `Compiler.codecache`, `VM.flags`.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `jfr metadata`, `summary` và lọc sự kiện recording.

**Điểm mấu chốt:** HotSpot **thực thi được ngay bằng interpreter**, **học hành vi runtime qua profile**, rồi **chi tiền biên dịch C1/C2 cho phần mã có lợi**; khi giả định về dữ liệu thay đổi, nó có thể **deopt và tối ưu lại** để luôn giữ kết quả Java đúng. Việc tối ưu phải được **quan sát theo workload thật**, không suy ra từ một đường chuyển tier tưởng tượng.
