# Giảm ví dụ lỗi thành trường hợp tái lập được (Java 15 và Java hiện đại)

> **Mục tiêu:** Biến một lỗi xuất hiện trong hệ thống Java lớn thành **trường hợp tái lập tối thiểu** (*minimal reproducible example*, MRE; còn gọi là *minimal complete verifiable example*, MCVE) mà người khác có thể biên dịch, chạy, nhìn thấy **đúng failure signature** và kiểm tra bản sửa. Bài thuộc nhóm **Chẩn đoán lỗi** của Java 15. Nội dung ưu tiên quy trình và các Java/JDK APIs **vẫn còn áp dụng trên Java hiện đại**; các ví dụ chạy độc lập với **JDK 17+**, không cần external dependencies hoặc framework test cụ thể. Các chương trình đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên OpenJDK 24.

## 1. “Lỗi có thật” chưa chắc đã là một trường hợp tái lập tốt

Một báo cáo sự cố như sau thường chưa đủ:

> “Service xử lý đơn hàng thỉnh thoảng trả HTTP 500. Lỗi xảy ra khi chạy trên máy A; tôi đã gửi cả repository và hàng nghìn dòng log. Có vẻ do Stream API.”

Vấn đề: người đọc chưa biết **đầu vào chính xác**, **đường chạy gây lỗi**, **phiên bản JDK**, **điều kiện môi trường**, **thực tế quan sát**, **kết quả kỳ vọng** và **cách kiểm tra lỗi vẫn tồn tại khi bỏ bớt thành phần**.

Một MRE tốt trả lời được:

1. **Minimal:** Còn **ít code, input và phụ thuộc nhất có thể**, nhưng vẫn tạo ra **cùng lỗi cần nghiên cứu**. “Tối thiểu” không chỉ là ít dòng: giữ mọi thứ **cần thiết để tái lập đúng vấn đề**.
2. **Reproducible:** Có **các bước rõ ràng** để người khác chạy lại và nhận failure tương tự trong cùng điều kiện.
3. **Complete:** Có đủ source, imports, dữ liệu test, version/dependencies và commands; không để người đọc đoán về class, database hoặc bí mật nội bộ.
4. **Verifiable:** Đo được khác biệt **expected vs actual** và xác nhận **đúng kiểu lỗi/đường code**, không phải một exception khác do bỏ mất cấu hình khi rút gọn.
5. **Safe to share:** Không chứa access tokens, mật khẩu, PII, production connection strings, dữ liệu khách hàng hoặc internal-only artifacts.

MRE là **phương tiện chẩn đoán**. Nó giúp tách nguyên nhân khỏi những noise của UI, HTTP gateway, database, logs và deployment. Nó không có nghĩa cần viết lại sản phẩm thành một app mới, và không phải mọi lỗi đều có thể tái lập chỉ với một file: đôi lúc điều kiện JVM/OS/thread scheduling/network thật **chính là phần bắt buộc của MRE**.

## 2. Từ một service lớn xuống một ví dụ Java: minh họa

Giả định một pipeline nhận dữ liệu:

~~~text
HTTP POST /orders
    ↓
JSON parser
    ↓
validation/auth
    ↓
repository/query
    ↓
Stream<OrderLine>
    ↓
Collectors.toMap(...)
    ↓
response serialization
    ↓
HTTP 500
~~~

Log gốc cho biết:

~~~text
java.lang.IllegalStateException: Duplicate key SKU-7
    at java.base/java.util.stream.Collectors...
    at ...OrderService.calculate...
~~~

Điều cần tìm không nhất thiết nằm ở HTTP, JSON parser, database hay token. Nếu stack trace và input cho thấy cùng `sku` xuất hiện hai lần, hãy đặt câu hỏi:

> “Lệnh `Collectors.toMap(Line::sku, Line::quantity)` trên hai bản ghi trùng key có tạo lại **chính IllegalStateException này** khi bỏ hoàn toàn HTTP/database không?”

Nếu **có**, một ví dụ hai phần tử trong `List.of(...)` có thể là MRE tốt hơn một bộ dữ liệu vài nghìn đơn hàng. Nếu **không**, đừng khẳng định đã giải thích lỗi; có thể parser, normalization, concurrency hoặc ordering mới là điều kiện gây sự cố.

**Nguyên tắc:** Giảm sự phức tạp **mỗi lần một yếu tố**, nhưng luôn chạy lại **failure predicate** sau mỗi bước. Bản rút gọn chỉ được chấp nhận nếu **vẫn có cùng lỗi**.

## 3. Định nghĩa failure predicate trước khi xóa code

Trước khi cắt bớt, viết một **tiêu chí tái lập** rõ ràng. Ví dụ:

| Thành phần | Giá trị cần giữ |
| --- | --- |
| Trigger | Hai dòng có cùng `sku="SKU-7"` |
| API lỗi | `Collectors.toMap(Line::sku, Line::quantity)` loại **không có merge function** |
| Thực tế | `IllegalStateException` khi collect |
| Kỳ vọng nghiệp vụ | Tổng số lượng hai dòng phải là 3 nếu chính sách cho phép gộp |
| Positive control | Một dòng `SKU-7` không gây exception |
| Negative/regression | Sau khi dùng merge policy phù hợp, hai dòng không còn exception |

**Đừng chỉ dùng “process exit code khác 0” làm điều kiện duy nhất**. Một MRE thiếu thư viện có thể lỗi `NoClassDefFoundError`, hoặc parse thất bại có thể lỗi `NumberFormatException`, vẫn exit code khác 0 nhưng **không phải lỗi gốc**.

Failure signature có thể gồm:

- Exception class và **root cause**; ví dụ `IllegalStateException`, `NullPointerException`, `ClassCastException`.
- Phương thức/đường code liên quan, không nhất thiết **line number** (line numbers dễ thay đổi khi rút gọn).
- Thông điệp exception **chỉ khi đó là hợp đồng ổn định**; nhiều thông điệp là implementation detail và đổi theo phiên bản.
- Dữ liệu đầu vào hoặc trạng thái quan trọng, ví dụ duplicate key, timezone, locale, encoding.
- Nếu là lỗi logic thay vì exception: một assertion **expected != actual**, ví dụ expected 2 nhưng actual 1.
- Nếu là lỗi đồng thời: một **interleaving cụ thể** có thể dẫn đến trạng thái sai, không chỉ “chạy 1000 lần đôi khi fail”.

**Failure predicate** càng cụ thể, thuật toán thu nhỏ input càng ít có nguy cơ giữ lại **lỗi khác tình cờ xuất hiện**.

## 4. Quy trình giảm lỗi có thể áp dụng cho Java backend

<escape>1.</escape> **Chụp hiện tượng:** ghi một failure cụ thể (stack trace, request class, input shape, module, timestamp, JVM flags, Java vendor/version). Không trích dữ liệu nhạy cảm vào bug report.

<escape>2.</escape> **Xác định đường tái lập:** chạy một command/test hiện tại tạo lỗi; lưu expected/actual và exit code. Nếu lỗi intermittent, đo tỉ lệ và điều kiện nó xảy ra trước khi sửa code.

<escape>3.</escape> **Khóa biến môi trường quan trọng:** chọn JDK, locale, timezone, charset, seed random, thread count, payload order, dependency versions. Chỉ khóa những yếu tố **được nghi ngờ**, không giả định mọi máy đều giống nhau.

<escape>4.</escape> **Cô lập điểm lỗi:** gọi trực tiếp method liên quan thay vì chạy toàn HTTP server, scheduler hoặc database nếu chúng **không cần thiết để giữ lỗi**.

<escape>5.</escape> **Thay phụ thuộc không liên quan:** thay repository bằng `List.of(...)`, thay network response bằng byte array/fixture, thay clock bằng input cố định, thay nguồn random bằng seed rõ ràng — **nhưng phải chạy lại lỗi** sau mỗi thay thế.

<escape>6.</escape> **Giảm dữ liệu trước:** thử bỏ batch/record/field/property. Với bài duplicate key, giữ **hai dòng trùng key**; một dòng là positive control.

<escape>7.</escape> **Giảm code:** xóa logging, framework wiring, phương thức không liên quan, class trung gian, annotation và dependencies không cần. Tránh xóa chính logic, synchronization hoặc state gây lỗi.

<escape>8.</escape> **Xác minh lại failure signature:** cùng exception/root cause hoặc cùng violation. Nếu symptom khác, hoàn tác bước vừa giảm hoặc tìm yếu tố bị mất.

<escape>9.</escape> **Thêm control và kiểm thử hồi quy:** trường hợp không lỗi phải pass; trường hợp tối thiểu phải fail trước fix và pass sau fix. Không sửa code khi chưa chứng minh MRE giữ được lỗi gốc.

<escape>10.</escape> **Đóng gói để người khác chạy:** tên file, Java version, lệnh compile/run, output chính, input, expected/actual, platform constraints và chính xác phần nào đã được loại khỏi hệ thống gốc.

### Sơ đồ quyết định ngắn

~~~text
Bắt đầu với lỗi đã quan sát
          |
          v
     Định nghĩa failure predicate
          |
          v
     Bỏ một thành phần / giảm input
          |
          v
     Chạy lại đúng failure predicate
          |
     +----+-----------------+
     |                      |
  Còn đúng lỗi?           Mất/đổi lỗi?
     |                      |
    Có                    Không
     |                      |
 Giữ bước giảm        Khôi phục phần cần thiết
     |                      |
     +----> Tiếp tục đến khi không giảm thêm hữu ích
                         |
                         v
       MRE + control + môi trường + lệnh + output
~~~

**Không biến việc minimization thành quá trình “xóa theo trực giác” mà không có test.** Một bước xóa nhỏ có thể thay thứ tự xử lý, giải phóng một lock, loại bỏ dữ liệu trùng, hoặc khiến JIT/compiler tối ưu khác; các thay đổi này có thể làm lỗi biến mất.

## 5. Ví dụ chạy độc lập thứ nhất: Collectors.toMap gặp duplicate key

Đây là lỗi thuần dữ liệu, **tái lập deterministic**, không cần database, mạng, thread hay random.

Tạo file **DuplicateKeyRepro.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DuplicateKeyRepro {
    record Line(String sku, int quantity) {}

    static Map<String, Integer> totals(List<Line> lines) {
        return lines.stream().collect(
                Collectors.toMap(Line::sku, Line::quantity));
    }

    public static void main(String[] args) {
        List<Line> input = args.length > 0 && args[0].equals("bad")
                ? List.of(new Line("SKU-7", 1), new Line("SKU-7", 2))
                : List.of(new Line("SKU-7", 1));

        Map<String, Integer> result = totals(input);
        System.out.println("entries=" + result.size());
        System.out.println("SKU-7=" + result.get("SKU-7"));
    }
}
~~~

**Biên dịch Java 17+:**

~~~bash
javac --release 17 -encoding UTF-8 DuplicateKeyRepro.java
~~~

**Positive control — một dòng:**

~~~bash
java DuplicateKeyRepro good
~~~

Stdout đã chạy thực tế:

~~~text
entries=1
SKU-7=1
~~~

**Negative/failing case — hai dòng trùng key:**

~~~bash
java DuplicateKeyRepro bad
~~~

Kết quả đã kiểm chứng:

- Process kết thúc với **exit code 1** trên JVM thử nghiệm.
- Lỗi gốc là **`java.lang.IllegalStateException`**.
- Dòng thông điệp cốt lõi trong stack trace:

~~~text
Exception in thread "main" java.lang.IllegalStateException: Duplicate key SKU-7 (attempted merging values 1 and 2)
~~~

**Không sao chép nguyên stack frame/line numbers của một bản compile khác để so tuyệt đối.** Số dòng nguồn, JDK implementation và wrapper của shell có thể khác, nhưng **contract `Collectors.toMap(keyMapper,valueMapper)` ném IllegalStateException với duplicate keys** còn áp dụng trong JDK hiện đại. Trên PowerShell, ngoại lệ có thể có thêm tiền tố dạng `java.exe :` của shell khi redirect stderr; đó **không phải** message do `Collectors` tạo.

### Tại sao chỉ hai bản ghi vẫn giữ nguyên bug?

- Mapped key của hai records đều là `"SKU-7"`.
- `Collectors.toMap` overload hai tham số **không quy định merge function**; nếu keys bằng nhau theo `Object.equals`, collector ném `IllegalStateException`.
- Việc có 2.000 đơn hàng trong database không quan trọng **nếu** chỉ cần 2 phần tử cùng key để gây lỗi.
- Nếu 1 record, không có collision → pass.
- Nếu 2 records khác key, collector cũng không gặp duplicate key → pass.

**Điểm đặc biệt:** Đây không phải lỗi do `HashMap` “không cho duplicate” theo nghĩa chung. Map có **một giá trị cho mỗi key**; chính overload `Collectors.toMap` đã chọn **throwing merge behavior** khi gặp key trùng. Có những overload `toMap` cho phép truyền merge function để xử lý va chạm có chủ đích.

## 6. Kiểm tra bản sửa mà không che giấu lỗi gốc

Nếu nghiệp vụ thực sự muốn **gộp số lượng** các dòng cùng `sku`, sử dụng merge function. Tạo file **DuplicateKeyFixed.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class DuplicateKeyFixed {
    record Line(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("SKU-7", 1),
                new Line("SKU-7", 2));

        Map<String, Integer> totals = lines.stream().collect(
                Collectors.toMap(
                        Line::sku,
                        Line::quantity,
                        Integer::sum,
                        TreeMap::new));

        System.out.println("entries=" + totals.size());
        System.out.println("SKU-7=" + totals.get("SKU-7"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 DuplicateKeyFixed.java
java DuplicateKeyFixed
~~~

Stdout đã kiểm chứng:

~~~text
entries=1
SKU-7=3
~~~

**Giải thích:**

- `Integer::sum` là **merge function theo policy ví dụ**; khi cùng key, cộng 1 và 2.
- `TreeMap::new` xác định kiểu Map để thứ tự khi duyệt keys được sắp xếp theo comparator mặc định. Nó không bắt buộc để sửa duplicate key; được đưa vào để cho thấy việc chọn Map type là một quyết định riêng.
- Bản sửa chỉ đúng nếu hợp đồng nghiệp vụ **cho phép cộng số lượng**. Nếu duplicate key biểu thị dữ liệu sai, cách sửa thích hợp có thể là **validate và trả lỗi nghiệp vụ**, không được âm thầm gộp.
- Positive control và failing MRE cũ phải được giữ làm **regression test**. Không xóa test chỉ vì code đã sửa.

**Trình tự an toàn:** trước fix → reproducer đỏ vì **đúng lỗi** → sửa nguyên nhân → reproducer xanh cho policy mới → chạy regression test rộng hơn. Nếu bỏ qua bước kiểm chứng trước fix, bạn có thể “sửa” một hiện tượng tình cờ không liên quan.

## 7. Tối thiểu không phải tối giản sai ngữ nghĩa

Có ba mức giảm:

| Mức | Ví dụ | Đánh giá |
| --- | --- | --- |
| **Quá lớn** | HTTP server + database + JSON + vài nghìn rows + security filters | Có thể tái lập, nhưng nhiều noise, khó bàn giao |
| **Đúng MRE** | `List.of(Line("SKU-7",1), Line("SKU-7",2))` → `Collectors.toMap` | Giữ điều kiện gây lỗi, đủ để chứng minh |
| **Quá nhỏ** | Chỉ `throw new IllegalStateException("Duplicate key")` | Sai: tái tạo **message** chứ không tái tạo bug của collector |

Thêm một ví dụ **rút gọn sai**:

~~~java
// Sai mục đích: tự tạo exception giống lỗi thay vì giữ nguyên hành vi cần nghiên cứu.
throw new IllegalStateException("Duplicate key SKU-7");
~~~

Đoạn này có thể tạo stack trace, nhưng **không còn dùng `Collectors.toMap`, không có duplicate-key mapping**. Nó không chứng minh lỗi gốc và không thể kiểm tra bản sửa merge policy.

**MRE không nhất thiết chỉ có 5 dòng.** Nếu bug cần 2 threads, JVM argument, một entrypoint, một fixture file hoặc một dependency version cụ thể, giữ chúng lại là đúng. Mục tiêu là **phần nhỏ nhất vẫn mang cùng quan hệ nhân quả**, không phải số dòng ngắn nhất bằng mọi giá.

## 8. Input minimization: giảm phần tử một cách có kiểm soát

Một trường hợp dữ liệu lớn có thể có hàng nghìn records. Cách đơn giản:

1. Xác định hàm `sameFailure(input)` trả true chỉ khi lỗi cần tìm còn xảy ra.
2. Xóa một record, chạy lại predicate.
3. Nếu vẫn true, **giữ bản đã xóa**.
4. Nếu false, **khôi phục record**.
5. Lặp tới khi không thể xóa **một** record nào nữa mà vẫn giữ lỗi.

Đây là **greedy single-element deletion**. Kết quả được gọi là **1-minimal** theo phép xóa một đơn vị: bỏ bất kỳ một phần tử nào trong kết quả cuối cũng mất lỗi. **1-minimal không có nghĩa global minimum**, vì đôi khi phải xóa **nhiều phần tử cùng lúc** để đến một trường hợp ngắn hơn.

### Failure predicate phải đủ chính xác

Trong bản demo sau, chỉ có **một thao tác trong test có thể ném IllegalStateException từ duplicate key**, nên bắt đúng class đó phù hợp để minh họa thuật toán. Trong dự án thật, **không bắt `Throwable` rồi trả true cho mọi lỗi**: khi xóa dữ liệu, một `NullPointerException` mới có thể xuất hiện do fixture hỏng, và thuật toán minimizer nhầm rằng vẫn giữ “cùng lỗi”.

Hãy quan sát **root cause, top application frame và đặc điểm trigger**, đồng thời không phụ thuộc line number hoặc wording không ổn định của exception message.

## 9. Chương trình chạy độc lập thứ hai: tự rút gọn input về 2 record

Tạo file **InputMinimizer.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class InputMinimizer {
    record Line(String sku, int qty) {}

    static boolean sameFailure(List<Line> lines) {
        try {
            Map<String, Integer> ignored = lines.stream().collect(
                    Collectors.toMap(Line::sku, Line::qty));
            return false;
        } catch (IllegalStateException expectedDuplicate) {
            return true;
        }
    }

    static List<Line> minimize(List<Line> initial) {
        List<Line> current = new ArrayList<>(initial);
        boolean changed;
        do {
            changed = false;
            for (int i = 0; i < current.size(); i++) {
                List<Line> trial = new ArrayList<>(current);
                trial.remove(i);
                if (sameFailure(trial)) {
                    current = trial;
                    changed = true;
                    break;
                }
            }
        } while (changed);
        return current;
    }

    public static void main(String[] args) {
        List<Line> full = List.of(
                new Line("noise-1", 91),
                new Line("SKU-7", 1),
                new Line("noise-2", 92),
                new Line("SKU-7", 2),
                new Line("noise-3", 93),
                new Line("noise-4", 94));

        List<Line> small = minimize(full);
        boolean oneMinimal = true;
        for (int i = 0; i < small.size(); i++) {
            List<Line> withoutOne = new ArrayList<>(small);
            withoutOne.remove(i);
            if (sameFailure(withoutOne)) {
                oneMinimal = false;
            }
        }

        System.out.println("initialSize=" + full.size());
        System.out.println("originalFails=" + sameFailure(full));
        System.out.println("minimalSize=" + small.size());
        System.out.println("minimalFails=" + sameFailure(small));
        System.out.println("oneMinimal=" + oneMinimal);
        for (Line line : small) {
            System.out.println(line.sku() + ":" + line.qty());
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 InputMinimizer.java
java InputMinimizer
~~~

Stdout đã được kiểm chứng:

~~~text
initialSize=6
originalFails=true
minimalSize=2
minimalFails=true
oneMinimal=true
SKU-7:1
SKU-7:2
~~~

### Vì sao kết quả là 2?

Bốn records `noise-*` không gây duplicate key, nên mỗi bản đều **có thể bỏ** mà lỗi vẫn xảy ra. Hai records `SKU-7` là điều kiện tối thiểu của lỗi được xét: chỉ giữ một trong hai thì không còn duplicate key.

**Cần hiểu giới hạn của thuật toán:**

- Nó chỉ thử **xóa một record**, chưa thử **rút gọn từng field** hoặc **giá trị chuỗi/number**.
- Nó không tối ưu về số lần gọi test trên tập dữ liệu rất lớn; với dữ liệu lớn, dùng **delta debugging (ddmin)** chia thành chunks và test các subsets/complements để giảm số lần chạy.
- Với input có thứ tự quan trọng, một thao tác “remove” phải **giữ thứ tự các phần tử còn lại**, như `ArrayList.remove(i)`. Không tự sort input rồi tuyên bố vẫn cùng bug.
- Nếu predicate chậm hoặc có side effects, nên **isolate mỗi test run** và cleanup trạng thái; tránh test thứ n ảnh hưởng test thứ n+1.
- Nếu predicate chỉ kiểm tra mọi exception là “fail”, có thể dẫn tới **false minimization**: một input rất ngắn gây lỗi mới chứ không phải lỗi cần tìm.
- `oneMinimal=true` chỉ chứng minh **không xóa thêm được một record** trong kết quả, không chứng minh không tồn tại một input 1-record hoặc 2-record khác gây một loại lỗi khác.

## 10. Delta debugging với test nhiều lần: làm sao biết đang giảm đúng?

Ý tưởng **ddmin**: chia input thành nhiều phần, thử **mỗi phần hoặc phần bù**, chỉ giữ giảm kích thước khi **cùng failure predicate** còn true. Tăng/giảm granularity khi không thể loại bỏ chunks hiện tại.

Ví dụ trước khi giảm:

~~~text
[A, B, C, D, E, F, G, H]
          |
          | test [A,B,C,D] và [E,F,G,H], rồi complements
          v
[A,B,D,H]       (nếu vẫn đúng failure)
          |
          | tiếp tục test chunks nhỏ hơn
          v
[B,H]           (nếu đây là hai điều kiện cần)
~~~

**Đây là sơ đồ thuật toán minh họa**, không phải output của `InputMinimizer` ở mục 9. Với dữ liệu thật, input chunks có thể chứa dependencies; loại bỏ một chunk phải **giữ input hợp lệ và giữ cùng môi trường**.

### Tiêu chí dừng hữu ích

- Với records: không bỏ thêm record nào mà vẫn giữ lỗi (1-minimal).
- Với chuỗi: không bỏ thêm substring/character cần thiết, nhưng phải **không phá encode/grammar** nếu bug yêu cầu dữ liệu hợp lệ.
- Với AST/JSON: không bỏ thêm field/node/predicate hợp lệ mà vẫn giữ lỗi.
- Với concurrency: không thể bỏ một thread/op/synchronization primitive bắt buộc mà vẫn thấy cùng interleaving gây lỗi.
- Với dependencies: không bỏ thêm library/module nào khỏi classpath mà vẫn có đúng failure.
- Với môi trường: xác định option/JDK behavior **gây sự khác biệt**, không làm mọi thành phần đổi cùng lúc.

**Không phải bài nào cũng nên tối thiểu hóa tự động**: nếu thời gian startup test đắt đỏ, có side effects lên dữ liệu thật, hoặc số trạng thái rất lớn, bắt đầu bằng thủ công và một predicate rõ ràng; chỉ chạy giảm dữ liệu trên **fixtures test/sandbox** đã cô lập.

## 11. Lỗi đồng thời: “thỉnh thoảng lỗi” cần một lịch thực thi có kiểm soát

Một bug đọc–sửa–ghi có thể rất hiếm khi chỉ chạy bình thường:

~~~java
int snapshot = counter.value;  // read
int updated = snapshot + 1;    // calculate
counter.value = updated;       // write
~~~

Hai threads cùng thực hiện ba bước trên **không tạo thành một increment nguyên tử**. Ngay cả nếu `value` là `volatile`, chỉ có visibility/ordering tương ứng; thao tác **read-modify-write** vẫn không được atomic hóa thành một khối.

Lịch gây lost update:

~~~text
Ban đầu: counter.value = 0

Thread A: read value -> 0
Thread B: read value -> 0
Thread A: write 0 + 1 -> 1
Thread B: write 0 + 1 -> 1

Kỳ vọng hai increments: 2
Thực tế:              1
~~~

Một cách kiểm thử tệ là thêm `Thread.sleep(100)` rồi hy vọng hai threads đủ gần nhau. **Sleep không cam kết thread nào đã chạy tới đúng điểm**; CI nhanh/chậm có thể tạo kết quả khác. Hãy dùng **CyclicBarrier, CountDownLatch, Phaser hoặc hook test** để buộc interleaving quan trọng xảy ra.

## 12. Chương trình chạy độc lập thứ ba: tái lập lost update bằng CyclicBarrier

Tạo file **LostUpdateRepro.java**:

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LostUpdateRepro {
    static final class Counter {
        volatile int value;
    }

    public static void main(String[] args) throws Exception {
        Counter broken = new Counter();
        CyclicBarrier afterRead = new CyclicBarrier(2);

        Runnable incrementWrong = () -> {
            int snapshot = broken.value;
            try {
                afterRead.await(5, TimeUnit.SECONDS);
            } catch (Exception e) {
                throw new IllegalStateException("Barrier failed", e);
            }
            broken.value = snapshot + 1;
        };

        Thread first = new Thread(incrementWrong, "increment-1");
        Thread second = new Thread(incrementWrong, "increment-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("expected=2");
        System.out.println("actual=" + broken.value);
        System.out.println("lostUpdateReproduced=" + (broken.value == 1));

        AtomicInteger fixed = new AtomicInteger();
        Thread fixedFirst = new Thread(fixed::incrementAndGet);
        Thread fixedSecond = new Thread(fixed::incrementAndGet);
        fixedFirst.start();
        fixedSecond.start();
        fixedFirst.join();
        fixedSecond.join();
        System.out.println("fixedActual=" + fixed.get());

        if (broken.value != 1 || fixed.get() != 2) {
            throw new AssertionError(
                    "Test did not reproduce the expected behavior");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 LostUpdateRepro.java
java LostUpdateRepro
~~~

Stdout đã được xác minh:

~~~text
expected=2
actual=1
lostUpdateReproduced=true
fixedActual=2
~~~

### Vì sao lịch này deterministic?

1. `Thread A` và `Thread B` mỗi người **đọc `broken.value` trước `afterRead.await(...)`**.
2. `CyclicBarrier(2)` chỉ cho phép cả hai rời barrier **sau khi cả hai đã đến**, nên cả hai đã lấy snapshot **0** trước khi một trong hai ghi kết quả.
3. Sau barrier, mỗi thread ghi **`snapshot+1`**, tức **1**, dù ai chạy trước.
4. `join()` giúp main thread chờ cả hai hoàn thành trước khi đọc/in kết quả.
5. `AtomicInteger.incrementAndGet()` cung cấp **atomic increment**, nên bản sửa in **2**.

Đây là **MRE đã ép một interleaving cụ thể**, không phải bằng chứng rằng mọi lịch thực thi của code gốc đều cho kết quả 1. Mục đích là chứng minh **có một lịch hợp lệ làm thất thoát increment**. Nếu lỗi production có thêm điều kiện, phải bảo đảm harness không loại bỏ nguyên nhân thật.

**Một chi tiết an toàn trong demo:** `await(5, TimeUnit.SECONDS)` tránh đợi vô hạn nếu một thread không tới barrier. Timeout/barrier bị hỏng ném exception và kết quả không được xem là pass. Trong CI thật, cần thu exceptions từ worker threads để báo đúng nguyên nhân thay vì chỉ dựa vào stdout. Cũng nên giới hạn `join`/timeout cả test khi không tin scheduler.

### Đừng dùng “thêm volatile” như sửa lỗi nguyên tử

`volatile` giúp visibility/ordering, **không** biến ba thao tác `read + add + write` thành atomic. Với counter, `AtomicInteger` hoặc critical section `synchronized`/`Lock` đúng cách thường phù hợp hơn. Việc dùng `CyclicBarrier` trong reproducer là **công cụ ép lịch test**, không phải fix nghiệp vụ.

## 13. Một lỗi chỉ xuất hiện trên một máy: hãy làm môi trường trở thành input

Không phải mọi lỗi đều thu nhỏ được chỉ bằng `List.of(...)`. Nhiều lỗi phụ thuộc **environmental inputs** mà code không nêu rõ:

| Biến môi trường | Triệu chứng thường thấy | Cách khóa khi tái lập |
| --- | --- | --- |
| **JDK version/vendor** | API khác, behavior provider/JIT/GC khác | Ghi `java -version`, `javac -version` và runtime flags |
| **Locale** | Lowercasing/sorting/formatting khác | `Locale.ROOT` cho machine keys hoặc truyền `Locale` rõ |
| **Timezone** | Ngày/giờ serialize hoặc parse khác | Truyền `ZoneId`/`Clock`, ghi zone khi test |
| **Charset** | Bytes khác, ký tự mojibake | `StandardCharsets.UTF_8`, `javac -encoding UTF-8` |
| **File separator/case sensitivity** | Đường dẫn hoạt động trên OS này nhưng fail OS kia | Dùng `Path`/`Files`, kiểm thử filesystem thật khi cần |
| **Classpath/module path** | `NoClassDefFoundError`, `ServiceLoader` khác | Khóa dependencies, build command và module names |
| **Order of records/hash iteration** | Kết quả không ổn định hoặc phụ thuộc order | Đưa input order cố định; không giả định `HashMap` iteration order |
| **Random seed** | Lỗi hiếm không quay lại | Seed rõ ràng trong test; ghi seed của lần fail |
| **Thread scheduling** | Lost update, races, deadlocks | Barrier/latch/harness tái tạo interleaving |
| **Network/database** | Timeout, transaction isolation, collation | Fake deterministic khi thay thế được; giữ service/container nếu nó là nguyên nhân |
| **Heap/GC/JIT flags** | Lỗi chỉ xảy ra khi tối ưu/pressure | Ghi flags thật, thay từng tham số theo test |
| **State/cache** | Chỉ fail sau chuỗi requests | Giữ sequence tối thiểu, reset state giữa runs |

**Tránh hứa tính tái lập tuyệt đối:** Phải ghi rõ phạm vi tái lập, ví dụ “reproduces trên JDK 17/21 với locale `tr-TR`”, hoặc “cần PostgreSQL collation X”. Nếu environment là nguyên nhân, xóa nó để thành one-file Java thuần có thể làm **mất chính lỗi cần chẩn đoán**.

## 14. Chương trình chạy độc lập thứ tư: lỗi do default Locale

Ví dụ nhiều sản phẩm dùng chuỗi như `"TITLE"` để tạo machine keys. `String.toLowerCase()` không tham số sử dụng **default Locale**; kết quả với chữ `I` trong tiếng Thổ Nhĩ Kỳ có thể khác en-US.

Tạo file **LocaleRepro.java**:

~~~java
import java.util.Locale;

public class LocaleRepro {
    public static void main(String[] args) {
        String input = "TITLE";
        String environmentDependent = input.toLowerCase();
        String stable = input.toLowerCase(Locale.ROOT);

        System.out.println("defaultLocale="
                + Locale.getDefault().toLanguageTag());
        System.out.println("defaultEqualsTitle="
                + environmentDependent.equals("title"));
        System.out.println("containsDotlessI="
                + environmentDependent.contains("\u0131"));
        System.out.println("rootEqualsTitle="
                + stable.equals("title"));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 LocaleRepro.java
~~~

**Run A — English/US:**

~~~bash
java '-Duser.language=en' '-Duser.country=US' LocaleRepro
~~~

Stdout đã kiểm chứng:

~~~text
defaultLocale=en-US
defaultEqualsTitle=true
containsDotlessI=false
rootEqualsTitle=true
~~~

**Run B — Turkish/TR:**

~~~bash
java '-Duser.language=tr' '-Duser.country=TR' LocaleRepro
~~~

Stdout đã kiểm chứng:

~~~text
defaultLocale=tr-TR
defaultEqualsTitle=false
containsDotlessI=true
rootEqualsTitle=true
~~~

### Đây có phải lỗi Java không?

**Không.** Đây là hành vi **đúng hợp đồng locale-sensitive lowercasing**. Lỗi nằm ở ứng dụng nếu nó **dùng output phụ thuộc default locale cho một machine key được yêu cầu bất biến**.

**Bản sửa theo hợp đồng ứng dụng:** Nếu identifier/canonical key cần independent với locale người dùng, sử dụng `toLowerCase(Locale.ROOT)`. Nếu đây là text hiển thị theo ngôn ngữ tự nhiên, có thể **cần** locale cụ thể của người dùng; không dùng `Locale.ROOT` vô điều kiện cho mọi quy tắc ngôn ngữ.

**Bài học về rút gọn:** Từ một bug “chỉ máy ở quốc gia X bị lỗi”, giữ lại **chuỗi input, default Locale và phép biến đổi**, bỏ database/HTTP/scheduler. Sau đó chạy hai môi trường đối chứng. Chỉ kết luận về nguyên nhân khi thay một yếu tố **Locale** làm kết quả đổi và MRE giữ đúng phenomenon.

### Lưu ý JVM flags và shell

- Các tham số `-Duser.language`/`-Duser.country` phải đứng **trước tên class** khi gọi `java`.
- Ví dụ đã quote các tham số như `'-Duser.language=tr'` để xử lý an toàn qua **PowerShell** (PowerShell có parsing đặc biệt với một số dạng arguments chứa dấu chấm và `=`); lệnh cũng dùng được trên shells thông thường.
- Nếu bug liên quan default locale được thay đổi **trong process** hoặc nhiều threads có cache locale, hãy thử **process mới** cho mỗi case để không mang state từ run trước.

## 15. Rút gọn theo tầng: dữ liệu, code, dependencies rồi môi trường

Một trình tự hiệu quả cho service backend Java:

| Tầng | Bản phức tạp | Bản nhỏ hơn cần thử | Điều không được làm mất |
| --- | --- | --- | --- |
| **UI/request** | Frontend, HTTP, auth gateway | Gọi trực tiếp service method | Input/headers/identity nếu ảnh hưởng bug |
| **Serialization** | JSON/XML/Protobuf payload dài | Fixture nhỏ hoặc object Java | Charset, normalization, field order cần thiết |
| **Business logic** | Nhiều classes, branching | Một method với parameters | Branch gây bug |
| **Persistence** | DB repository/transactions | In-memory list hoặc DB test | Isolation/collation/constraint nếu là nguyên nhân |
| **Concurrency** | Scheduled workers/pool đa luồng | Hai threads và barrier | Interleaving/happens-before quan trọng |
| **Runtime** | Nhiều JVM flags/modules | Chỉ các flags ảnh hưởng | Version, GC/JIT mode khi lỗi phụ thuộc chúng |
| **Deployment** | Kubernetes/multiple services | Một process, rồi container nếu cần | OS/network/permissions/timezone nếu thiết yếu |

**Không tự biến môi trường sai thành môi trường đúng khi giản lược.** Ví dụ bug có nguyên nhân từ **database transaction isolation** thì thay DB bằng `List.of(...)` có thể làm bug biến mất; MRE tối thiểu có thể cần **DB container + schema + hai transactions**, không phải một file Java.

### Quy tắc thay mocks/fakes

Mocks/fakes phù hợp khi:

- Chúng tái tạo **giá trị trả về giống hệt** mà code cần.
- Lỗi phát sinh ở logic **sau** dependency, không phụ thuộc timing/transaction semantics của dependency.
- Kết quả tái lập vẫn khớp failure predicate.

Mocks/fakes nguy hiểm khi:

- Mock trả thứ tự records khác DB thật.
- Mock response không phản ánh null, charset hoặc parser quirk.
- Timing stub xóa race condition cần điều tra.
- In-memory DB có isolation/collation khác RDBMS production.

**Thực dụng:** Nếu một dependency không thể loại bỏ, giữ nó lại trong một **container/service fixture nhỏ đã pin version**. MRE “complete” ưu tiên **đúng nguyên nhân** hơn “không có dependency”.

## 16. Lỗi không deterministic: thay xác suất bằng kiểm soát

Nếu chạy một test 1.000 lần thì fail 1 lần, có hai bài toán riêng:

1. **Cơ chế sai là gì?** Chẳng hạn lost update vì shared read-modify-write không atomic.
2. **Làm sao kích hoạt cơ chế ấy chủ động?** Chẳng hạn hai threads cùng đọc snapshot trước barrier, rồi cùng ghi.

**Chiến thuật theo loại lỗi:**

| Loại | Cách tăng tính tái lập có lý do |
| --- | --- |
| Thread race | `CyclicBarrier`/`CountDownLatch`/`Phaser` hoặc test hook để ép thứ tự; không dựa vào `sleep` |
| Random input | Ghi seed; truyền `new Random(seed)` vào code cần test nếu API cho phép |
| Clock-sensitive | Truyền `Clock.fixed(...)`/`Clock.offset(...)`; tránh `Instant.now()` rải rác |
| Timezone | Truyền `ZoneId.of(...)`, không dùng ngầm default zone |
| Locale | `Locale.ROOT` hoặc `Locale.forLanguageTag(...)` theo contract |
| Filesystem | Test với temp directories và file names cụ thể, cleanup đúng owner |
| Network delay | Mô phỏng timeout khi logic thuộc application; dùng local test server/containers khi behavior mạng quan trọng |
| Classpath/class loading | Pin versions, làm sạch output build, chỉ định module/classpath rõ |
| GC/JIT | Giữ chính xác `java -version`/VM flags, test bản runtime liên quan |
| Trình tự request | Tạo một sequence nhỏ chính xác, reset process/state trước mỗi run |

**Đừng khiến test “deterministic” bằng cách thay thuật toán bị lỗi** trước khi tái lập. Test harness có thể đồng bộ lịch trong **đoạn harness**, nhưng code nghiệp vụ vẫn cần giữ thao tác read–modify–write sai thì mới chứng minh được nguyên nhân.

**Đừng dùng stress test thay thế MRE hoàn toàn.** Stress tests giúp tìm rủi ro khi chạy dài/nhiều threads; MRE deterministic giúp debug một **interleaving** cụ thể. Hai loại test **bổ sung cho nhau**.

## 17. Kiểm thử dương, âm và “mutation control”

Mỗi MRE nên có ít nhất:

- **Positive control:** Input hợp lệ, hành vi kỳ vọng pass. Ví dụ một `SKU-7` → `entries=1`.
- **Failing input:** Input tối thiểu tạo lỗi cũ. Ví dụ hai `SKU-7` → `IllegalStateException`.
- **One-change test:** Đổi đúng **một thuộc tính** trong failing input; ví dụ sửa key thứ hai thành `SKU-8`. Nếu lỗi biến mất, đó là bằng chứng duplicate key là yếu tố quan trọng.
- **Regression test sau fix:** Với chính failing input, code xử lý theo hợp đồng mới (gộp quantities, hoặc trả domain error rõ ràng).
- **Environment control:** Chạy cùng source dưới hai environments khác nhau nếu nghi ngờ locale/JDK/timezone.
- **Failure signature control:** Khi minimizer thấy fail, kiểm tra **đúng exception/cause**, không coi mọi non-zero exit là cùng bug.

### Ví dụ thêm một assert không dùng JUnit

Đoạn code sau là **minh họa trong method**, sử dụng `DuplicateKeyRepro` đã có trong cùng package/classpath:

~~~java
var two = java.util.List.of(
        new DuplicateKeyRepro.Line("SKU-7", 1),
        new DuplicateKeyRepro.Line("SKU-7", 2));

try {
    DuplicateKeyRepro.totals(two);
    throw new AssertionError("Expected duplicate-key failure");
} catch (IllegalStateException expected) {
    // Đúng kiểu exception do Collectors.toMap không có merge function.
}
~~~

**Không catch `AssertionError`** ở đoạn này. Nếu production code không còn ném đúng exception trước khi áp fix mà test cũ đang dùng để chứng minh bug, nó phải **báo lỗi kiểm thử**, không âm thầm pass.

**Sau fix** thì thay kỳ vọng `throws` bằng assertions với business result, ví dụ sum là 3. Nếu chính policy nghiệp vụ là “không cho duplicate”, test cần assert lỗi validation thuộc domain thay vì chỉ ném exception implementation của Stream API.

## 18. Thiết kế lệnh compile/run để người khác không phải đoán

**Bộ nguồn trong bài đều là file độc lập ở default package:**

~~~text
repro/
  DuplicateKeyRepro.java
  DuplicateKeyFixed.java
  InputMinimizer.java
  LostUpdateRepro.java
  LocaleRepro.java
~~~

Chúng dùng **Java SE APIs**, không cần Maven/Gradle, Docker hoặc dependency bên ngoài cho các trường hợp này.

**Biên dịch cả bộ:**

~~~bash
javac --release 17 -encoding UTF-8 DuplicateKeyRepro.java DuplicateKeyFixed.java InputMinimizer.java LostUpdateRepro.java LocaleRepro.java
~~~

**Chạy:**

~~~bash
java DuplicateKeyRepro good
java DuplicateKeyRepro bad
java DuplicateKeyFixed
java InputMinimizer
java LostUpdateRepro
java '-Duser.language=en' '-Duser.country=US' LocaleRepro
java '-Duser.language=tr' '-Duser.country=TR' LocaleRepro
~~~

**Chú ý:** `java DuplicateKeyRepro bad` **cố ý ném exception và trả exit code khác 0**. Nếu dùng script có `set -e` hay PowerShell ErrorActionPreference nghiêm ngặt, cần ghi rõ **đây là failure được mong đợi**, hoặc dùng test harness bắt exception thay vì để pipeline ngừng trước khi chạy test sau.

**Không yêu cầu JUnit trong ví dụ** để tránh ràng buộc người học phải cấu hình thêm build tool/runner. Trong dự án thật có JUnit Jupiter hoặc thư viện test đã được duy trì, có thể viết `assertThrows(IllegalStateException.class, ...)` và các assertions khác tương ứng, nhưng phải có dependency/version phù hợp; đừng đưa mã JUnit giả định chạy được bằng `javac` thuần.

### Biến Java version ảnh hưởng những gì?

- `record` trong `DuplicateKeyRepro`/`InputMinimizer` là cú pháp **ổn định từ Java 16**, nên bộ source của bài đặt target **Java 17+**.
- `Stream`, `Collectors.toMap`, `CyclicBarrier`, `AtomicInteger`, `Locale.ROOT` đều là API ổn định vẫn dùng trên Java hiện đại.
- Chủ đề gắn với **Java 15** vì đây là module học tập, không có nghĩa `record` đang là final syntax trong Java 15. Muốn chạy đúng Java 15, thay `record` bằng class thường với constructor/getters; không cần cơ chế đã bị legacy.
- `javac --release 17` bảo đảm source/API/bytecode target Java 17, còn runtime có thể là Java 17 hoặc mới hơn, miễn tương thích.

## 19. Gói bug report/MRE để người khác review nhanh

Một bản bàn giao tốt nên có dạng:

~~~text
Title: Collectors.toMap duplicate key fails on two rows

Environment:
  JDK: OpenJDK 24.0.2, javac --release 17
  OS: Windows (test run); code uses only Java SE APIs
  Dependencies: none
  Charset: UTF-8 for Java source

Files:
  DuplicateKeyRepro.java
  DuplicateKeyFixed.java

Commands:
  javac --release 17 -encoding UTF-8 DuplicateKeyRepro.java DuplicateKeyFixed.java
  java DuplicateKeyRepro good
  java DuplicateKeyRepro bad
  java DuplicateKeyFixed

Expected:
  Two SKU-7 quantities should sum to 3 if duplicate lines are allowed.

Actual, before fix:
  IllegalStateException: Duplicate key SKU-7
  Failing Java invocation exits nonzero.

Control:
  Single SKU-7 row -> entries=1, SKU-7=1.

After applying intended merge policy:
  entries=1, SKU-7=3.

Suspected cause:
  Collectors.toMap(keyMapper, valueMapper) rejects duplicate mapped keys.

Security:
  Uses synthetic SKU and quantities, no production data.
~~~

Đây là **mẫu báo cáo dành cho case đã thử**, không phải file đính kèm có sẵn ở một repository. Nếu lỗi có security/sensitive scope, hãy sử dụng channels triage thích hợp; tuyệt đối không copy tokens, private keys hoặc toàn bộ production payload vào issue công khai.

### Đính kèm gì, bỏ gì?

**Nên đưa:** source MRE, input fixtures synthetic, 3–10 dòng exception/stack trace liên quan, Java version/build, commands, observed outputs, test controls và dependency manifest nếu cần.

**Không nên đưa:** toàn repository khi có thể tránh, stack trace 20.000 dòng không lọc, private env vars, customer data, tokens/cookies, keys, các assumptions (“chắc chắn lỗi JVM”) chưa được chứng minh hoặc một screenshot không thể copy commands.

**Đủ tái lập quan trọng hơn đẹp:** một README ngắn, copy-paste được với source code, input và command thường hữu ích hơn video dài mà không thấy code đầy đủ.

## 20. Khi nào không thể “bỏ hết framework và database”?

Một số bug cần một môi trường tối thiểu **nhiều thành phần**:

### Transaction isolation / database collation

Nếu cùng SQL query trả thứ tự khác vì collation hoặc bug chỉ xảy ra khi hai transactions interleave, mock `List.of(...)` **có thể khiến lỗi biến mất**. Giữ DB với version/schema tối thiểu, một seed fixture, transaction boundary và query thực.

### Serialization/encoding

Nếu bug liên quan UTF-8, Unicode normalization hoặc serializer, giữ **raw bytes** và encode/decode path gây lỗi. Chuyển sang String object quá sớm có thể mất byte-level trigger.

### Classpath/ServiceLoader

Nếu lỗi phát sinh do provider discovery hoặc phiên bản dependency, giữ dependency artifact và lệnh classpath/module path tối thiểu. `NoSuchMethodError` thường cần đúng **binary version mismatch**, không thể luôn thu nhỏ thành Java source thuần mà vẫn là cùng lỗi.

### Native/JVM GC/JIT

Nếu behavior phụ thuộc JDK/OS/architecture/VM options, **đừng bỏ các flags quan trọng**. Nhưng cũng không đưa 100 JVM flags từ production khi chỉ 1–2 flags có liên quan: giảm bằng A/B có kiểm chứng.

### Distributed protocol/race

Nếu bug chỉ xảy ra do hai services gửi messages theo một thứ tự cụ thể, cần giữ **hai endpoints và thứ tự events tối thiểu**, có thể dùng fake network hoặc Docker Compose fixture. Không loại bỏ phân tán rồi thay bằng một method trực tiếp nếu điều đó thay đổi consistency/timeouts.

**Định nghĩa MRE linh hoạt:** ít phụ thuộc nhất **mà vẫn tái lập cùng lỗi**, không nhất thiết “một file Java” trong mọi trường hợp.

## 21. Triage lỗi: thông tin nào có giá trị chẩn đoán cao nhất?

| Dữ liệu | Vì sao hữu ích |
| --- | --- |
| Exception class/root cause | Tách lỗi Java API, data, logic, IO, runtime |
| Application stack frame gần nguồn | Khoanh method/branch khả nghi |
| Exactly failing input | Giảm biến không liên quan |
| Expected vs actual | Phân biệt bug với hành vi đúng của thư viện |
| Java/JDK vendor/build | Phân biệt hỗ trợ API, exception messages, runtime behavior |
| Dependency versions | Lỗi binary compatibility / code path khác |
| Locale/timezone/charset | Bắt input ẩn có thể đổi kết quả |
| Thread schedule / synchronization | Tái lập intermittent race |
| JVM options/OS restrictions | Cần với GC/JIT/native/FS/network bugs |
| Repro frequency | Chỉ số chất lượng reproducer, không chỉ pass một lần |
| Control input passes? | Chứng minh trigger không phải do môi trường test hỏng |
| Run command + working directory | Người khác tái lập mà không đoán |
| Fix mutation passes? | Regression proof, không chỉ tự nhận “đã sửa” |

### Nếu có nhiều exception trong log

Lỗi đầu tiên nhìn thấy trong log chưa chắc là **root cause**. Ví dụ HTTP 500 có thể là wrapper exception, còn `Caused by` bên dưới là `IllegalStateException` của Stream. Khi rút gọn, nên giữ **root cause cùng call path** thay vì chỉ ép một wrapper exception xuất hiện.

Tuy nhiên, không tự bỏ wrapper nếu **chính wrapper behavior** là bug (ví dụ retry policy bắt nhầm exception type). MRE phải phản ánh **câu hỏi đang chẩn đoán**, không phải một quy tắc xóa wrapper cố định.

## 22. Những lỗi phổ biến khi thu nhỏ reproducer

1. **Đã nhìn thấy symptom nhưng chưa có command chạy lại.** Người khác không xác định được khi nào “pass/fail”.
2. **Chỉ đếm exit code khác 0.** Mọi lỗi compile hoặc thiếu dependency cũng bị xem là “cùng bug”.
3. **Bắt `Throwable` rồi return true trong minimizer.** Có thể giữ một exception mới hoàn toàn không liên quan.
4. **Chỉ assert nguyên văn exception message.** Wording implementation có thể thay đổi giữa các Java releases.
5. **Xóa record trùng trước khi test.** Bug biến mất nhưng người viết vẫn kết luận “đã giảm thành công”.
6. **Thay `Collectors.toMap` bằng `throw new IllegalStateException(...)`.** Chỉ nhái message, không giữ bug.
7. **Giảm code và data cùng lúc.** Không biết thao tác nào làm lỗi biến mất.
8. **Mock dependency làm thay đổi ordering/transactions.** Đánh mất điều kiện cần của lỗi.
9. **Sửa bug trong lúc viết MRE.** Không có baseline đỏ để chứng minh.
10. **Bỏ positive control.** Một reproducer luôn fail dù input nào cũng có thể chỉ là harness hỏng.
11. **Dùng `Thread.sleep` làm “đồng bộ” hai threads.** Kết quả phụ thuộc scheduler, dễ flaky.
12. **Cho rằng `volatile` làm ++ thành atomic.** Read–modify–write vẫn có lost update.
13. **Không giới hạn waits/timeouts ở test concurrency.** Một failure có thể treo CI vô thời hạn.
14. **Không kiểm tra lỗi trong worker threads.** Main thread có thể in “pass” dù worker đã crash.
15. **Ép chạy loop nhiều lần mà không ghi rate.** Một failure 1/10.000 runs chưa phải MRE đáng tin nếu chưa điều khiển được trigger.
16. **Tái lập lỗi locale nhưng không ghi default locale.** Người khác chạy ngôn ngữ khác và không thấy bug.
17. **Dùng `String.toLowerCase()` mặc định cho identifier bất biến.** Phụ thuộc ngôn ngữ người dùng.
18. **Đọc text từ bytes bằng default charset.** Lỗi phụ thuộc runtime/OS, không giữ được input nguyên bản.
19. **Tin vào iteration order của `HashMap`.** Không có contract ordering cho mục đích đó.
20. **Rút gọn input nhưng thay đổi thứ tự phần tử.** Có thể mất lỗi dựa trên encounter order.
21. **Xóa tất cả logs/stack trace.** Mất dữ liệu để đối chiếu đúng failure signature.
22. **Thử trên JDK khác mà không ghi version.** Có thể đổi code path hoặc thông điệp lỗi.
23. **Mang dữ liệu production thật vào issue công khai.** Vi phạm bảo mật; nên tạo fixture synthetic cùng cấu trúc.
24. **Chỉ giữ một exception mà thiếu expected behavior.** Chưa xác định đó là bug hay contract đúng.
25. **Cố tối ưu số dòng bằng mọi giá.** Bỏ luôn điều kiện cần của lỗi; MRE vô nghĩa.
26. **Tự coi 1-minimal là toàn cục tối ưu.** Greedy minimizer không đảm bảo global minimum.
27. **Không reset state giữa các lần thử.** Mỗi phép thử phụ thuộc side effects của lần trước.
28. **Đoán “Java bug” ngay khi thấy IllegalStateException.** Phải đọc API contract và tối thiểu hóa trigger trước.
29. **Chỉ xem fix chạy trên một positive input.** Failing input cũ phải được dùng làm regression test.
30. **Tổng kết kết quả mà không đưa source/lệnh.** Người khác không thể xác minh độc lập.

## 23. Kiểm tra tính tái lập trên CI và giữa các JDK

Khi đã có MRE:

1. **Cold start:** chạy một JVM process mới, không dựa vào static state từ test trước.
2. **Build clean:** compile nguồn theo commands rõ; xóa output classes cũ trong **sandbox/test directory của bạn** nếu cần.
3. **Run controls:** positive input phải thành công; failing input phải tạo đúng failure.
4. **Test different JDKs:** nếu yêu cầu hỗ trợ 17/21/25, chạy trên mỗi JDK production target, ghi version/vendor. Không lấy output một bản làm cam kết cho mọi bản.
5. **Pin dependencies:** với Gradle/Maven dự án thật, sử dụng version/lock files; MRE của bài chỉ Java SE nên không cần.
6. **Repeat flaky tests:** ghi số lần runs và failure rate. Nếu có thể, chuyển sang deterministic event/barrier.
7. **Regression after fix:** chạy test fail cũ cùng với broader suite để tránh bỏ sót lỗi logic mới.
8. **Avoid destructive tests:** nếu MRE cần DB/files/network, chạy với fixture, temp directory, account/test service và cleanup.
9. **Keep artifacts concise:** source, commands, logs cốt lõi, seed, môi trường, expected/actual; không làm mất thông tin quan trọng.
10. **Document known limitations:** ví dụ thread interleaving nhân tạo chứng minh khả năng lost update, **không chứng minh service production luôn lỗi ở lịch đó**.

### Đếm tái lập bằng một bộ test không phụ thuộc framework

Với `DuplicateKeyRepro`, chạy positive case và failing case trong hai process độc lập. Trên Bash/PowerShell, ghi lại exit code của từng lần theo đúng shell bạn dùng và assert failure signature. **Đừng dùng một regex chỉ kiểm tra từ `Exception` trong stderr**; cần xác nhận loại/đường code liên quan.

Khi đã chuyển sang JUnit (hoặc test runner hiện đại tương đương), ưu tiên assertions trực tiếp trên exception class, message contract nếu ổn định, state/output và dataset. Tránh kết hợp test “must fail” với một shell command làm CI tự kết luận pipeline thất bại mà không phân biệt đây là **expected negative test**.

## 24. Bài luyện tập theo cấp độ

**Bài 1 — Bóc lớp ứng dụng.** Một HTTP 500 có root cause `Collectors.toMap` duplicate key. **Đạt** khi bỏ được HTTP/database khỏi reproducer mà vẫn ném `IllegalStateException` trong collector.

**Bài 2 — Positive control.** Từ hai records trùng `SKU-7`, thử xóa một record. **Đạt** khi case một record pass và hiểu rằng **sự trùng khóa** là điều kiện kích hoạt.

**Bài 3 — Phân biệt nguyên nhân với symptom.** Dùng `throw new IllegalStateException(...)` thay `Collectors.toMap`. **Đạt** khi chỉ ra nó **không phải cùng reproducer** dù message giống.

**Bài 4 — Regression chính sách gộp.** Sử dụng `Collectors.toMap(...,Integer::sum)`. **Đạt** khi hai quantities 1 và 2 cho 3; nêu trường hợp policy cần **reject duplicates** thay vì gộp.

**Bài 5 — Thu nhỏ dữ liệu tự động.** Chạy `InputMinimizer` và thêm 10 noise records. **Đạt** khi kết quả còn hai `SKU-7` và `oneMinimal=true`.

**Bài 6 — 1-minimal vs global.** Giải thích vì sao greedy deletion không đảm bảo input ngắn nhất toàn cục. **Đạt** khi nêu được trường hợp phải xóa **cả nhóm phần tử** để tạo reduction mới.

**Bài 7 — Failure predicate an toàn.** Thêm một `NumberFormatException` vào bước parse giả định. **Đạt** khi minimizer không coi exception mới là cùng lỗi duplicate key.

**Bài 8 — Race deterministic.** Chạy `LostUpdateRepro`. **Đạt** khi thấy `actual=1` dù có hai threads, giải thích `CyclicBarrier` giữ hai snapshots cùng 0.

**Bài 9 — Sửa race.** Thay read–modify–write bằng `AtomicInteger.incrementAndGet()` hoặc một critical section phù hợp. **Đạt** khi expected=2/actual=2 ở bản sửa, không cho rằng `volatile` là đủ.

**Bài 10 — Locale bug.** Chạy `LocaleRepro` với `en-US` và `tr-TR`. **Đạt** khi biết `toLowerCase()` mặc định phụ thuộc locale, còn `toLowerCase(Locale.ROOT)` ổn định cho machine identifiers theo policy này.

**Bài 11 — Timezone.** Một bug parse ngày chỉ xuất hiện tại một timezone. **Đạt** khi tạo test với `ZoneId`/`Clock` tường minh, không dựa vào ngày giờ local của máy kiểm thử.

**Bài 12 — Charset.** Một chuỗi tiếng Việt bị lỗi khi gửi/nhận qua bytes. **Đạt** khi rút gọn thành `byte[]` + encode/decode với `StandardCharsets.UTF_8` và mô tả khác biệt input bytes.

**Bài 13 — Giữ DB khi cần.** Một lỗi transaction chỉ xảy ra do concurrent updates trong RDBMS. **Đạt** khi biết không được thay DB bằng `List.of(...)` nếu điều đó làm mất transaction isolation condition.

**Bài 14 — Bộ hồ sơ bàn giao.** Viết một bug report dưới 1 trang gồm Java version, files, commands, expected/actual, controls và failure signature. **Đạt** khi người khác clone/copy fixture và tái lập mà không hỏi thêm những điều kiện thiết yếu.

**Bài 15 — CI test chắc chắn.** Dùng negative test `DuplicateKeyRepro bad`. **Đạt** khi runner hiểu “exception này được mong đợi”, không đánh đồng với compile failure hoặc NoClassDefFoundError.

**Bài 16 — Input privacy.** Một payload production có emails, tokens, addresses. **Đạt** khi tạo synthetic fixture giữ cấu trúc/độ dài/encoding liên quan nhưng loại PII/secrets, rồi xác minh vẫn có cùng bug.

**Bài 17 — Khi cắt quá tay.** Bỏ một JVM option và bug biến mất. **Đạt** khi hoàn tác bước giảm, thêm option đó vào MRE và chứng minh quan hệ nhân quả bằng đối chứng.

**Bài 18 — Nâng cấp JDK.** Lỗi chỉ xuất hiện ở một bản Java vendor/build. **Đạt** khi test same code/data trên 2 versions, ghi precise environment thay vì quy mọi khác biệt là “lỗi ngẫu nhiên”.

## 25. Checklist cuối cùng trước khi nộp MRE

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Đã có failure cụ thể chưa? | Exception/logic mismatch kèm expected vs actual |
| Có chính xác câu lệnh chạy? | `javac`/`java` hoặc build tool commands đầy đủ |
| Source complete chưa? | Class, imports, main method/test và dữ liệu cần thiết |
| Dùng API đang hỗ trợ? | Java SE stable, JDK target hợp lệ, không internal/legacy hacks |
| Có Java version/vendor? | `java -version`, `javac -version` |
| Có positive control? | Case không lỗi phải pass |
| Có failing case? | Phải giữ **cùng bug** và kiểm được bằng test |
| Failure signature đủ chặt? | Không chỉ nonzero exit / broad Throwable |
| Có rút gọn đầu vào? | Không thể xóa thêm phần quan trọng mà vẫn giữ trigger |
| Có giữ thứ tự/state quan trọng? | Có, nếu bug phụ thuộc chúng |
| Có khóa locale/timezone/seed? | Có khi chúng ảnh hưởng behavior |
| Nếu concurrency? | Có interleaving/happens-before được điều khiển |
| Nếu cần DB/network? | Fixture/container tối thiểu và version pinned |
| Có dọn dữ liệu nhạy cảm? | Không PII/secrets/internal tokens |
| Có output được kiểm chứng? | Stdout chính xác, stacktrace core và exit code |
| Có regression test sau fix? | Failing input cũ phải qua contract mới |
| Có ghi hạn chế? | Không claim deterministic tuyệt đối/hoàn toàn portable nếu chưa xác nhận |

## 26. Nguồn chính thức và tiếp tục học

- [Oracle Java SE 25 — Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toMap` overload hai tham số ném `IllegalStateException` nếu mapped keys trùng; overload ba tham số cho phép merge policy.
- [Oracle Java SE 25 — CyclicBarrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): cho phép các threads chờ nhau tại một barrier, hỗ trợ timed waits và memory-consistency effects.
- [Oracle Java SE 25 — AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `incrementAndGet()` là thao tác tăng nguyên tử.
- [Oracle Java SE 25 — java.util.concurrent package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html): `happens-before` và các synchronization utilities.
- [Java Language Specification SE 25, Chapter 17](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): threads, locks, volatile, data races, memory model.
- [Oracle Java SE 25 — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `toLowerCase()` và `toLowerCase(Locale)`, ví dụ trường hợp locale-sensitive.
- [Oracle Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): default Locale và `Locale.ROOT`.
- [Oracle Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release` và `-encoding`.
- [Oracle Java SE 25 — java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM system properties, version, diagnostics và runtime options.
- [Oracle Java SE 25 — Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `start()`, `join()` và luồng thực thi.
- [Oracle Java SE 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): `record` là ngôn ngữ ổn định từ Java 16; bài dùng target Java 17+.
- [Oracle Java SE 25 — StandardCharsets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): chỉ rõ UTF-8 thay vì phụ thuộc default encoding.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/): `assertThrows`, parameterized tests, test execution; chỉ dùng khi dự án đã cấu hình dependency phù hợp, không phải yêu cầu của các chương trình Java SE thuần ở bài này.

**Ghi nhớ:** Rút gọn lỗi không phải “xóa code cho thật ít”, mà là giữ được **cùng failure predicate** sau mỗi lần bỏ bớt input/code/dependency/môi trường. Một MRE tốt có **failing case tối thiểu, positive control, commands chạy lại, Java/environment versions và output đáng tin**. Với lỗi đồng thời, kiểm soát **interleaving**; với lỗi chỉ có trên một máy, đưa **locale/timezone/charset/JDK flags** trở thành input tường minh. Chỉ sửa bug sau khi đã có một trường hợp tái lập được, rồi **biến chính trường hợp ấy thành regression test**.
