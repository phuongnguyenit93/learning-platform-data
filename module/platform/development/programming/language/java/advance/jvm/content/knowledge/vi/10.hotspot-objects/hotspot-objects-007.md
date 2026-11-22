# Compact Strings, string interning và string deduplication: ba cơ chế, ba mục đích khác nhau

`String` là một kiểu bất biến (immutable) và xuất hiện với mật độ rất cao trong chương trình Java: khóa JSON, HTTP headers, log messages, tên trường, mã trạng thái, giá trị cấu hình và các dòng văn bản từ database. Khi quan sát heap của **HotSpot**, ta thường gặp ba cơ chế tối ưu liên quan String:

1. **Compact Strings** giảm bộ nhớ dùng để **biểu diễn ký tự bên trong một đối tượng String** khi nội dung có thể mã hóa bằng Latin-1.
2. **String interning** cung cấp một **đối tượng String chuẩn (canonical object)** cho các chuỗi có cùng nội dung, thông qua literal/constant pool và API `String.intern()`.
3. **String deduplication** là tối ưu hóa của bộ thu gom rác: các **đối tượng String vẫn khác nhau**, nhưng có thể **dùng chung mảng dữ liệu ký tự phía sau** khi các mảng giống nhau.

Ba cơ chế này **không thay thế nhau**. Compact Strings không làm hai String object trở thành cùng một object; interning thay đổi reference người gọi nhận về; còn deduplication hoạt động bên trong runtime và **không làm biểu thức `a == b` từ `false` thành `true`** cho hai object riêng biệt.

Nội dung dưới đây phân biệt **ngữ nghĩa công khai của Java** với **chi tiết triển khai HotSpot**, giải thích JVM memory layout một cách có giới hạn, minh họa bằng **Java 17+ chạy được** và hướng dẫn kiểm tra/tối ưu có số liệu thay vì dựa vào suy đoán.

## 1. Trước hết: String là immutable, còn reference có identity

Trong Java, mỗi biến kiểu `String` chứa **reference** tới một đối tượng String, hoặc `null`. Chuỗi ký tự mà String biểu diễn là **bất biến** theo hợp đồng API: một lời gọi như `concat`, `replace` hoặc `toUpperCase` không chỉnh sửa nội dung ký tự của String đã tồn tại.

```java
String first = "cache";
String second = first;
String third = new String("cache");
```

Ở đây:

- `first == second` là `true` vì cả hai giữ **cùng reference**.
- `first.equals(third)` là `true` vì hai String biểu diễn **cùng nội dung**.
- `first == third` là `false` vì `new String(...)` đã tạo String object riêng.
- Chuỗi nội dung bất biến cho phép runtime chia sẻ backing storage một cách an toàn **khi không làm thay đổi các ngữ nghĩa Java có thể quan sát**.

**`==` với hai String references kiểm tra object identity**, không kiểm tra văn bản. Trong code nghiệp vụ, dùng `equals` khi mục tiêu là so sánh nội dung, kể cả khi ứng dụng có bật interning hoặc string deduplication.

### 1.1. Hai “đơn vị chia sẻ” khác nhau

```text
Chuỗi A và B có nội dung "cache"

A) String objects riêng, backing arrays riêng:
   a ──► String@A ──► byte[] #1 = "cache"
   b ──► String@B ──► byte[] #2 = "cache"
        a != b       các arrays chứa bytes giống nhau

B) Interning (nếu caller dùng reference do intern trả về):
   a.intern() ──┐
                ├──► canonical String@C ──► backing array #C
   b.intern() ──┘
        cùng một String object khi so references kết quả

C) Deduplication:
   a ──► String@A ──┐
                    ├──► cùng backing byte[] #D
   b ──► String@B ──┘
        a != b, nhưng storage dữ liệu có thể được chia sẻ
```

Sơ đồ này là **mô hình khái niệm của HotSpot hiện đại**, không phải định dạng bộ nhớ mà Java Language Specification bắt buộc mọi JVM dùng.

## 2. Compact Strings: giảm kích thước dữ liệu của MỖI chuỗi

### 2.1. Từ `char[]` sang `byte[]` có thông tin mã hóa

Trước JDK 9, nhiều triển khai `java.lang.String` của OpenJDK dùng backing `char[]`, với mỗi phần tử 16 bit. **JEP 254 — Compact Strings** (JDK 9) chuyển HotSpot/OpenJDK String sang dạng nội bộ hiệu quả hơn, về mặt khái niệm:

```text
String object trong HotSpot JDK 17 (minh họa)
┌───────────────────────────────────┐
│ object header và những field khác │
│ reference "value" ───────────┐    │
│ coder = LATIN1 hoặc UTF16    │    │
└───────────────────────────────┼────┘
                                ▼
                          byte[] value
                          mã hóa LATIN1 / UTF16
```

- Nếu toàn bộ **UTF-16 code units** trong String biểu diễn được trong khoảng `U+0000..U+00FF`, HotSpot có thể dùng **LATIN1 coder**, khoảng **1 byte cho mỗi code unit** ở backing data.
- Nếu không biểu diễn được bằng LATIN1, HotSpot dùng **UTF16 coder**, khoảng **2 byte cho mỗi UTF-16 code unit** ở backing data.
- Field nội bộ `byte[] value` và `byte coder` là **chi tiết của HotSpot/OpenJDK**, không phải public Java API hay một layout bắt buộc cho mọi JVM.
- Bất kể coder, Java API của `String` vẫn tuân theo **UTF-16 semantics**: `length()` và `charAt` dựa trên code units; không chuyển thành đơn vị byte chỉ vì nội bộ là LATIN1.

“Compact” ở đây **không** có nghĩa String chuyển sang UTF-8 chung cho mọi nội dung. LATIN1 ở HotSpot là chế độ 1 byte cho các UTF-16 code units có giá trị tối đa 255; nếu cần ký tự khác thì dùng internal UTF16 representation.

### 2.2. Ví dụ Latin-1, ký tự châu Á và emoji

| Nội dung | Java `length()` | Code points | HotSpot Compact Strings thường chọn | Dữ liệu ký tự minh họa |
| --- | ---: | ---: | --- | --- |
| `"Hello"` | 5 | 5 | LATIN1 | Khoảng 5 bytes |
| `"café"` (é = U+00E9) | 4 | 4 | LATIN1 | Khoảng 4 bytes |
| `"雪"` (U+96EA) | 1 | 1 | UTF16 | Khoảng 2 bytes |
| `"😀"` (U+1F600) | 2 | 1 | UTF16 | Khoảng 4 bytes |

Các con số cột cuối chỉ ước lượng **payload của backing array**; **không bao gồm** header đối tượng String, header của byte array, alignment, reference fields, compressed oops hoặc những object khác. Vì vậy không được nói chuỗi `"Hello"` chiếm tổng cộng 5 bytes heap.

Emoji có một Unicode code point ngoài Basic Multilingual Plane nhưng chiếm **hai UTF-16 code units** (surrogate pair); đây là ví dụ rõ nhất vì sao không thể đồng nhất `length()` với số ký tự hiển thị.

### 2.3. Chương trình Java 17 quan sát được gì?

Tạo tệp **`CompactTextDemo.java`**:

```java
public class CompactTextDemo {
    public static void main(String[] args) {
        String latin = "café";
        String cjk = "雪";
        String emoji = "😀";

        System.out.println("latinLength=" + latin.length());
        System.out.println("cjkLength=" + cjk.length());
        System.out.println("emojiLength=" + emoji.length());
        System.out.println("emojiCodePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("latinCharAt3=" + latin.charAt(3));
        System.out.println("cjkCharAt0=" + cjk.charAt(0));
    }
}
```

Chạy với JDK 17+ trong môi trường terminal hỗ trợ Unicode:

```bash
javac --release 17 -encoding UTF-8 CompactTextDemo.java
java -Dfile.encoding=UTF-8 CompactTextDemo
```

**Stdout theo nội dung Java (giả định terminal hiển thị Unicode chính xác):**

```text
latinLength=4
cjkLength=1
emojiLength=2
emojiCodePoints=1
latinCharAt3=é
cjkCharAt0=雪
```

Điều ví dụ này **chứng minh bằng API** là cách `String.length()` / `charAt` / `codePointCount` hoạt động, không phải “đo byte[] value trực tiếp”. Java không công bố public method để hỏi String đang được HotSpot gắn coder LATIN1 hay UTF16. Muốn khảo sát layout nội bộ cần công cụ chuyên dụng/JVM knowledge và tuân thủ ràng buộc modules; không dựa vào reflection `--add-opens` như một API ổn định.

### 2.4. Vì sao `getBytes(StandardCharsets.UTF_8)` không trả lời coder nội bộ?

`getBytes` **mã hóa văn bản ra một byte array mới theo charset yêu cầu của caller**. Nó không có nghĩa trả trực tiếp `value` nội bộ của String. Ví dụ một String nội bộ LATIN1 vẫn có thể sinh UTF-8 nhiều byte hơn cho chữ `é`.

```java
import java.nio.charset.StandardCharsets;

String text = "café";
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
int utf16Bytes = text.getBytes(StandardCharsets.UTF_16BE).length;
// UTF-8: 5 bytes; UTF-16BE: 8 bytes cho ví dụ này.
```

Đây là **đoạn mã minh họa**, không phải file chạy riêng. `"café"` dùng 4 UTF-16 code units, nhưng trong UTF-8 chữ `é` chiếm hai bytes. Không suy byte[] backing của HotSpot từ một `getBytes` result.

### 2.5. Chi phí và giới hạn của Compact Strings

Ưu điểm thường kỳ vọng:

- Với các ứng dụng chứa nhiều Latin-1 strings, giảm payload từ xấp xỉ 2 bytes/code unit về 1 byte/code unit.
- Ít bytes hơn để copy/quét và ít heap pressure trong các tình huống phù hợp.
- Những cơ chế String functions/intrinsics của HotSpot hỗ trợ cả LATIN1 và UTF16 để giữ nguyên Java semantics.

Giới hạn:

- String có **ít nhất một code unit > U+00FF** cần UTF16 coder trong cơ chế này; không phải nửa chuỗi nén Latin-1 và nửa còn lại UTF16 trên cùng backing value.
- String objects và byte-array headers vẫn có overhead.
- Một số hoạt động cần xét coder/chuyển đổi và có chi phí CPU; lợi ích hiệu năng phải đo theo workload.
- Compact Strings **không xử lý trùng lặp giữa các String objects**; nhiều String `"same"` xây dựng độc lập vẫn có thể giữ nhiều backing arrays trước khi có cơ chế dedup riêng.

### 2.6. Cờ HotSpot `-XX:-CompactStrings`

Trên một số bản HotSpot/OpenJDK hỗ trợ (bao gồm JDK 17), Compact Strings được bật mặc định và có cờ chẩn đoán để **vô hiệu hóa**:

```bash
java -XX:-CompactStrings -cp . CompactTextDemo
```

Hành vi Java API và stdout ví dụ **phải giữ nguyên**; điều thay đổi là lựa chọn encoding/data layout nội bộ của HotSpot. Không sử dụng cờ này để “sửa” ký tự Unicode hoặc charset của file: lỗi console encoding và codec I/O phải được giải quyết ở nơi tương ứng.

## 3. String interning: chia sẻ CANONICAL String OBJECT

### 3.1. Contract của `intern()`

`String.intern()` là **public Java API** trả về canonical representation của một chuỗi. Theo tài liệu `java.lang.String`:

- Nếu intern pool đã có String cùng nội dung theo `equals`, `intern()` trả reference tới String canonical đang ở pool.
- Nếu chưa có, String được thêm vào pool và một canonical reference được trả.
- Với hai Strings `s`, `t`: **`s.intern() == t.intern()` khi và chỉ khi `s.equals(t)`**.
- **String literals** và kết quả string-valued constant expressions được intern theo quy tắc ngôn ngữ.

Đây là **hợp đồng về identity của kết quả intern**, không phải cơ chế tự động thay biến local đã trỏ tới object khác.

Ví dụ:

```java
String a = new String("same");
String b = new String("same");

boolean content = a.equals(b);         // true
boolean identity = (a == b);           // false
boolean canonical = (a.intern() == b.intern()); // true
```

Dù đã gọi `intern()`, các biến `a` và `b` vẫn trỏ tới **các object ban đầu**; `intern()` không “sửa reference trong biến” hay biến tất cả existing String objects thành một.

### 3.2. Literal, constant expression và runtime concatenation

```java
String literalA = "hello";
String literalB = "he" + "llo";
String runtime = new StringBuilder().append("he").append("llo").toString();
```

- `"he" + "llo"` là **compile-time constant expression** nên biểu diễn giá trị canonical như literal `"hello"`; `literalA == literalB` là `true`.
- `runtime` có nội dung bằng `"hello"` nhưng được dựng tại runtime, nên không bắt buộc trỏ tới object literal.
- `runtime.intern()` trả canonical String có nội dung `"hello"`, mà literal đã cung cấp, nên kết quả `== literalA` là `true`.

**Đừng suy rằng mọi phép `+` tạo String mới**: constant folding có thể xảy ra tại compile time; optimizer cũng có thể đơn giản hóa runtime expressions khi không làm thay đổi hành vi quan sát. Khi dạy object identity, nên dùng ví dụ explicit `new String`, nơi constructor call buộc tạo object mới theo semantics của `new`.

### 3.3. Chương trình runnable với stdout xác định

Tạo tệp **`InterningDemo.java`**:

```java
public class InterningDemo {
    public static void main(String[] args) {
        String literal = "shared";
        String folded = "sha" + "red";
        String a = new String("shared");
        String b = new String(new char[] {'s','h','a','r','e','d'});

        System.out.println("literal==folded=" + (literal == folded));
        System.out.println("a.equals(b)=" + a.equals(b));
        System.out.println("a==b=" + (a == b));
        System.out.println("a==literal=" + (a == literal));

        String ca = a.intern();
        String cb = b.intern();

        System.out.println("ca==cb=" + (ca == cb));
        System.out.println("ca==literal=" + (ca == literal));
        System.out.println("a==b after intern=" + (a == b));
    }
}
```

Lệnh:

```bash
javac --release 17 InterningDemo.java
java InterningDemo
```

**Stdout chính xác:**

```text
literal==folded=true
a.equals(b)=true
a==b=false
a==literal=false
ca==cb=true
ca==literal=true
a==b after intern=false
```

Câu cuối cực kỳ quan trọng: sau lời gọi `intern`, **chỉ `ca` và `cb` mới giữ kết quả canonical**. Interning không chuyển `a` và `b` sang cùng object khi ta vẫn giữ hai references cũ.

### 3.4. Intern pool có nằm trong Java heap không?

Có sự khác biệt giữa **ngữ nghĩa API** và chi tiết memory layout theo JDK release. Với HotSpot hiện đại, canonical `String` objects là Java objects được quản lý trên heap; HotSpot có cơ cấu StringTable/handles phục vụ lookup. **Không** áp dụng máy móc sơ đồ “interned strings luôn nằm trong Permanent Generation và tồn tại vĩnh viễn” của những thế hệ HotSpot cũ cho Java 17.

Không nên phụ thuộc vào địa chỉ/thiết kế bảng băm, khả năng GC thu hồi entries hoặc tối ưu lớp loader cụ thể để quyết định semantics của `intern()`. Hợp đồng public là **canonical identity theo nội dung khi dùng kết quả intern**.

### 3.5. Khi nào chủ động intern?

Có thể cân nhắc khi:

- Có **tập từ vựng nhỏ, lặp lại mạnh và tương đối ổn định**: ví dụ tên trạng thái, event type, key schema hoặc type labels.
- Đã **đo profiler/heap dump** và thấy có nhiều String objects trùng lặp, không dễ tái sử dụng bằng cấu trúc dữ liệu nghiệp vụ tốt hơn.
- Có chiến lược quản lý retention/throughput phù hợp, tránh tạo áp lực quá lớn lên StringTable.

Không nên mặc định intern tất cả input chưa kiểm soát từ HTTP request, log line, UUID, session token, random identifiers hoặc chuỗi high-cardinality. Nhiều giá trị duy nhất khiến chi phí lookup/housekeeping cao mà **không** có nhiều đối tượng để chia sẻ.

**Interning không phải cách mã hóa String**, không phải public “free memory” API, và không nên dùng như một thay thế cho `equals` hay cấu trúc cache có lifecycle/eviction rõ ràng.

## 4. String deduplication: chia sẻ BACKING ARRAYS, không gộp object

### 4.1. Ý tưởng của JEP 192 và HotSpot G1

**String Deduplication** (JEP 192, được đưa vào HotSpot G1 từ dòng JDK 8) phát hiện nhiều `String` objects mang **nội dung dữ liệu backing giống nhau** và cố gắng cho chúng dùng chung backing storage.

Trong JDK 8 thời điểm tính năng ra đời, String thường lưu trong `char[]`. Với **HotSpot JDK 17 sau Compact Strings**, nội dung nằm trong **`byte[] value`**, nên giải thích cho JDK 17 cần nói **backing byte arrays**, không phải nói mọi String hiện đại vẫn dùng `char[]`.

```text
TRƯỚC deduplication:
  reference a ──► String@A ──► byte[] #1 = [72,101,108,108,111]
  reference b ──► String@B ──► byte[] #2 = [72,101,108,108,111]
                            (hai mảng chứa bytes giống nhau)

SAU deduplication (nếu GC chọn hai đối tượng phù hợp):
  reference a ──► String@A ──┐
                             ├──► byte[] #1 = [72,101,108,108,111]
  reference b ──► String@B ──┘
  byte[] #2 có thể không còn được giữ bởi các String đó.

  a == b vẫn FALSE; a.equals(b) vẫn TRUE.
```

**Cái được chia sẻ là mảng dữ liệu**, không phải việc biến `String@B` thành `String@A`. Nếu GC tự động merge object identities, logic Java dùng `==`, object monitors hay `System.identityHashCode` có thể quan sát thay đổi; đó không phải mục tiêu của String Deduplication.

### 4.2. Có đảm bảo mọi chuỗi trùng lặp sẽ bị dedup?

**Không.** Đây là **tối ưu implementation/GC**, không phải tính năng ngữ nghĩa bắt buộc của Java.

Trong HotSpot G1, GC thường sàng lọc **candidate String objects** theo điều kiện tuổi và các giai đoạn xử lý, sau đó thực hiện tra cứu/bổ sung vào bảng dedup riêng. Việc dedup có thể chạy **đồng thời** và phụ thuộc GC cycles, object liveness, độ trùng lặp và các ngưỡng.

Hệ quả:

- Hai String trùng nhau có thể **chưa** được dedup ngay sau khi được tạo.
- Không có Java API chuẩn `String.isDeduplicated()` để ứng dụng biết trạng thái backing array.
- `System.gc()` **chỉ là lời yêu cầu/hint** đối với GC, không đảm bảo mọi candidate được dedup trước khi lệnh trả về.
- Cùng một chương trình có thể cho các số liệu dedup khác nhau ở hai lần chạy, hai heap sizes, hai JVM configs.
- Dedup giúp giảm heap live set khi nhiều backing arrays giống nhau còn tồn tại; nó cũng tiêu tốn CPU, metadata/table processing và có trade-offs.

### 4.3. Bật trên HotSpot JDK 17 với G1

Theo tài liệu lệnh `java` JDK 17, tùy chọn:

- **`-XX:+UseStringDeduplication`** bật string deduplication.
- Trên JDK 17 HotSpot, cơ chế được tài liệu hỗ trợ với **G1 GC**, nên bật `-XX:+UseG1GC` để minh bạch.
- Tùy chọn này **mặc định tắt** trên JDK 17.
- **`-Xlog:stringdedup*=debug`** yêu cầu Unified Logging ghi thông tin string deduplication, nhưng output/định dạng tùy JVM và GC activity.

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload
```

Đây là lệnh chuyên cho **HotSpot JDK 17**. Các JVM/GC khác hoặc release sau có thể có hỗ trợ/cờ mặc định khác; xác minh `java -version` và tài liệu đúng bản đang dùng. Bật flag **không** bảo đảm một con số tiết kiệm bộ nhớ cố định.

### 4.4. Chương trình tạo nhiều String objects trùng nội dung

Tạo tệp **`DedupWorkload.java`**:

```java
public class DedupWorkload {
    private static volatile String[] keepAlive;

    public static void main(String[] args) {
        String[] values = new String[200_000];

        for (int i = 0; i < values.length; i++) {
            String content = "status-" + (i % 8);
            values[i] = new String(content.toCharArray());
        }

        keepAlive = values;
        System.out.println("objects=" + values.length);
        System.out.println("contentEqual=" + values[0].equals(values[8]));
        System.out.println("sameObject=" + (values[0] == values[8]));

        System.gc();
        System.out.println("gcRequested");
    }
}
```

Biên dịch:

```bash
javac --release 17 DedupWorkload.java
```

Chạy bình thường:

```bash
java DedupWorkload
```

**Stdout từ mã ứng dụng (không tính logs bổ sung của JVM):**

```text
objects=200000
contentEqual=true
sameObject=false
gcRequested
```

Giải thích:

1. Có **200.000 String references** trong một mảng còn reachable qua `keepAlive`.
2. Chỉ có **8 nội dung khác nhau**: `status-0` tới `status-7`.
3. `new String(content.toCharArray())` tạo các String objects riêng biệt từ dữ liệu chars; khi Compact Strings bật, chúng thường dùng LATIN1 payload, nhưng ban đầu có cơ hội tồn tại nhiều backing arrays trùng nhau.
4. `values[0]` và `values[8]` có nội dung bằng nhau nhưng là **hai object riêng biệt**. String dedup, nếu diễn ra, không đổi `==`.
5. `System.gc()` không phải phép chờ bảo đảm dedup hoàn tất; `gcRequested` chỉ xác nhận code đã **gọi GC hint**.

### 4.5. Đọc logging đúng cách

Chạy với G1 + dedup logging:

```bash
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload
```

Kết quả **application stdout** vẫn có bốn dòng như trên, nhưng **log của JVM không có định dạng hoặc số lượng dòng cố định**; output có thể nhiều hơn và chạy trước/giữa các dòng in. Tùy độ tuổi object, GC cycles, thời gian thực thi, không nhất thiết đã thấy lượng bytes tiết kiệm đáng kể ngay khi chương trình kết thúc.

Nếu cần benchmark đúng:

- Giữ tập String objects còn sống đủ lâu qua nhiều GC cycles theo điều kiện workload.
- Dùng nhiều lần đo và cùng JDK/GC/heap settings khi so sánh bật/tắt.
- Đọc heap snapshots/histograms và các metrics GC phù hợp; phân biệt retained heap, total allocations và pause/CPU costs.
- Không coi số lượng String objects giảm đi là mục tiêu chính của dedup: **object count có thể không thay đổi**, còn backing byte arrays/retained memory mới là thứ giảm.
- Không ép gọi `System.gc()` liên tục trong production chỉ để kích hoạt cơ chế này.

## 5. Bảng so sánh ba cơ chế theo đúng đơn vị tiết kiệm

| Tiêu chí | Compact Strings | `intern()` | String deduplication |
| --- | --- | --- | --- |
| Lớp cơ chế | HotSpot/String internal representation | Public `String.intern()` + JVM literal canonicalization | HotSpot GC optimization |
| Mục tiêu | Giảm **bytes trên một backing value** khi content phù hợp Latin-1 | Tái dùng **cùng một String object** cho nội dung bằng nhau | Tái dùng **cùng backing array** giữa các String objects riêng |
| Khi xảy ra | Khi String được tạo/chuyển đổi theo representation phù hợp | Khi xử lý literal/constant hoặc caller gọi `intern()` | Khi GC nhận dạng và xử lý candidates |
| Cần code caller chủ động? | Không đối với default HotSpot behavior | Có để chủ động intern runtime Strings; literal tự intern | Thường bật VM flag, không sửa Java source |
| Thay đổi `a == b` của hai objects ban đầu? | Không | Không tự thay hai refs cũ; **kết quả `a.intern() == b.intern()` đúng theo nội dung** | Không |
| Giảm String object headers? | Không do bản thân Compact Strings | Có cơ hội tái sử dụng **một** canonical object khi ứng dụng giữ kết quả | Không |
| Giảm duplicated backing arrays? | Giảm kích thước từng array, **không gộp** các array trùng | Khi dùng canonical object, dùng backing array của object đó | **Có thể** chia sẻ cùng byte[] giữa nhiều objects |
| Semantics/API | Không thay đổi public String behavior | Có thể quan sát canonical identity của kết quả | **Không thay đổi kết quả Java-level identity/equality** |
| Trade-off | Coder handling/encoding, layout-specific overhead | StringTable lookup, retention, GC/throughput | Candidate scanning, dedup table CPU/memory, GC work |
| Định vị cho JDK 17 | JEP 254 / HotSpot default | Java `String` API, JLS literals | JEP 192, G1 với `UseStringDeduplication` |

**Phân biệt “số đối tượng” với “kích thước dữ liệu”:** một triệu Strings ngắn có cùng nội dung có thể tiết kiệm theo hai hướng rất khác nhau. Interning trả cùng object để nhiều references cùng trỏ tới **một String**. Deduplication không đổi tổng số String instances, mà tìm cách giảm **số backing arrays giữ nội dung giống nhau**.

### 5.1. Ví dụ bộ nhớ minh họa

Giả sử có 100.000 String objects, mỗi object có nội dung Latin-1 dài 40 UTF-16 code units, và tạm **bỏ qua mọi headers, alignment và overhead**:

- Khi dùng dạng dữ liệu 16-bit cho mỗi code unit: payload một mảng khoảng **80 bytes**, tổng payload của 100.000 mảng khoảng **8 MB**.
- Với Compact Strings LATIN1: payload một mảng khoảng **40 bytes**, tổng khoảng **4 MB** nếu mỗi String còn backing array riêng.
- Nếu String dedup có thể cho tất cả các Strings có đúng một nội dung dùng chung array: payload duplicate có thể giảm rất mạnh; nhưng **100.000 String object headers vẫn còn**.
- Nếu ứng dụng thay các references bằng kết quả `intern()` của cùng nội dung, có thể giữ **một canonical String object** thay vì các object duplicate đã hết reachable; lượng memory thực tế lại phụ thuộc vòng đời, GC và các tham chiếu khác.

Đây chỉ là **phép tính payload minh họa** để thấy đơn vị khác nhau, **không phải dự báo RSS, committed heap, retained size, hay số byte GC log sẽ báo**.

## 6. Kết hợp Compact Strings, interning và dedup có xung đột không?

Về nguyên tắc, chúng có thể **cùng tồn tại** trong HotSpot:

```text
Java application
  │
  ├── tạo Strings
  │      └── Compact Strings chọn LATIN1/UTF16 backing payload phù hợp
  │
  ├── gọi intern() khi muốn canonical String
  │      └── caller dùng reference trả về từ StringTable
  │
  └── GC với string dedup enabled
         └── cố gắng nhận dạng các String/backing arrays giống nhau
             rồi giảm duplicated backing storage nơi có thể

Các ranh giới không đổi:
  - equals() so nội dung;
  - == so object identity;
  - public String API không lộ trực tiếp coder/byte[] identity;
  - JVM và GC có quyền chọn tối ưu nội bộ.
```

Không có một công thức “bật cả ba sẽ giảm đúng 75% RAM” cho mọi workload. Lợi ích phụ thuộc tỷ lệ Latin-1, độ dài và tính trùng lặp, lifecycle, kích thước heap, GC, StringTable pressure và object graph.

Nếu ứng dụng **đã chủ động dùng canonical references cho hầu hết các giá trị lặp**, số duplicate String objects còn lại ít hơn, khiến lợi ích thêm từ dedup có thể giảm. Nếu ứng dụng cần giữ các String objects riêng (ví dụ data transfer object giữ nhiều field), dedup vẫn có thể tiết kiệm các backing arrays mà không yêu cầu thay reference.

### 6.1. Vì sao không nên dùng `==` ngay cả khi hệ thống intern?

Một đoạn data có thể đến từ:

- String literal đã intern.
- JSON parser tạo object mới.
- Database/JDBC driver tạo String mới.
- Deserialization, reflection, JNI hoặc library tạo các object riêng.
- Thao tác runtime `substring`, `replace`, `StringBuilder.toString()`.

Không có bảo đảm **mọi producer** trả canonical object theo cùng chính sách. Nếu một đường dữ liệu quên intern, phép `==` có thể sai bất ngờ dù hai chuỗi có cùng văn bản. Dùng `equals` để so nội dung; chỉ dựa vào reference identity khi **thực sự đang quản lý một invariant canonicalization được kiểm soát rõ**.

### 6.2. Dedup không phải interning tự động

Một HotSpot G1 đã bật `UseStringDeduplication` không được đổi `a == b` của hai `new String(...)` từ false thành true, vì identity khác là điều Java chương trình có thể quan sát. Nó cũng không có nghĩa `s.intern()` trở nên thừa về mặt hợp đồng canonical references.

Thứ GC có thể đổi là **backing byte[] được object reference tới**, không phải identity của String objects.

## 7. Những gì `javap` có thể và không thể chứng minh

Dùng:

```bash
javac --release 17 CompactTextDemo.java InterningDemo.java DedupWorkload.java
javap -c -p InterningDemo
javap -c -p CompactTextDemo
```

Cần phân biệt ba tầng:

1. **Source-level behavior**: `String.intern()`, `equals()` và `length()` nằm trong public API.
2. **Bytecode-level operations**: `ldc` để tải String literal từ runtime constant pool, `new` / `invokespecial` tạo object, `invokevirtual String.intern` để gọi API.
3. **HotSpot internal layout và GC runtime**: `byte[] value` / `coder`, string dedup candidates/tables và GC logs.

`javap` có thể chỉ ra **`ldc`** trong mã tạo literal, **`new java/lang/String`** trong constructor và **`invokevirtual String.intern`** nơi gọi. Tuy nhiên `javap -c` **không phải heap inspector**: nó không in Coder hiện hành của object hay chứng minh hai Strings đã share backing array sau GC.

Nếu xem internal `String.value` qua reflective access với flags như `--add-opens java.base/java.lang=ALL-UNNAMED`, đó là **truy cập chi tiết không phải public contract**, có rủi ro khác giữa JDK releases. Không biến cách hack reflection đó thành hướng dẫn coding business logic.

## 8. Kịch bản thực tế: cân nhắc cơ chế nào?

### 8.1. Ứng dụng có nhiều tên field JSON ngắn, lặp đi lặp lại

- Compact Strings tự giúp giảm payload của tên field Latin-1.
- Nếu parser hoặc ứng dụng có **bảng tên field chuẩn nhỏ**, có thể cân nhắc canonicalization/interning hoặc cache được kiểm soát theo lifecycle.
- Nếu vẫn tạo nhiều String objects độc lập, G1 string dedup có thể giảm duplicated backing arrays.
- Trước khi bật/tối ưu, kiểm tra parser/library có cơ chế symbol canonicalization riêng không; làm hai lần có thể tăng overhead mà không giúp thêm.

### 8.2. Server tạo nhiều mã lỗi hoặc trạng thái giống nhau

Ví dụ `"SUCCESS"`, `"PENDING"`, `"FAILED"` xuất hiện nhiều trong objects. Nếu là literal được tái sử dụng trực tiếp thì Java vốn đã có canonical literals. Nếu đến từ network/database dưới dạng String mới, object identity vẫn khác; cần đánh giá intern/cache/dedup theo tỷ lệ lặp và retention.

Dù thế nào, dùng enum hoặc một value object có domain semantics rõ ràng đôi khi tốt hơn giữ hàng triệu raw Strings; đó là quyết định **thiết kế API**, không phải nhiệm vụ riêng của HotSpot GC.

### 8.3. Log messages, UUID và tokens hầu như duy nhất

Khi giá trị hiếm khi trùng nhau:

- Compact Strings vẫn có thể giảm payload nếu content là Latin-1.
- Interning khó tiết kiệm, vì gần như không có canonical references được dùng lại.
- String dedup có thể tốn CPU/table overhead nhưng tìm thấy ít duplicated content.

**Không** dùng `intern()` cho mọi HTTP header value, path chứa ID hay token tùy ý mà chưa có số liệu; đây có thể là high-cardinality unbounded workload.

### 8.4. Unicode đa ngôn ngữ, ký tự vượt Latin-1

Nếu phần lớn Strings chứa chữ Hán, chữ Nhật, emoji hoặc code units ngoài `U+00FF`:

- Compact Strings LATIN1 ít phát huy ở những Strings đó; chế độ UTF16 cần thiết theo biểu diễn HotSpot.
- Interning vẫn hoạt động theo **nội dung Unicode**, không phụ thuộc coder.
- Dedup vẫn có thể chia sẻ backing arrays **khi content trùng**, dù là UTF16 encoding.

**Đừng coi “UTF16 coder” là vấn đề Unicode correctness.** Nó là lựa chọn dữ liệu nội bộ cho ký tự mà LATIN1 không đủ khả năng biểu diễn.

## 9. Theo dõi chi phí trong HotSpot JDK 17

Dùng công cụ đo trước/sau với cùng input và cùng cấu hình:

```bash
# Baseline G1 (dedup mặc định tắt trên JDK 17):
java -XX:+UseG1GC DedupWorkload

# Bật dedup và xem log của HotSpot:
java -XX:+UseG1GC -XX:+UseStringDeduplication -Xlog:stringdedup*=debug DedupWorkload

# So hành vi String API, CompactStrings bật/tắt:
java CompactTextDemo
java -XX:-CompactStrings CompactTextDemo

# Kiểm tra cờ phù hợp trong HotSpot đang dùng:
java -XX:+PrintFlagsFinal -version
```

Để giải thích một số liệu bộ nhớ, phải chỉ rõ đang đo:

- **Heap allocated bytes:** lượng data được tạo trong một khoảng thời gian.
- **Heap live set/retained size:** data còn reachable sau GC tại thời điểm quan sát.
- **Process RSS:** bao gồm heap committed, native allocations, stacks, code cache và nhiều loại memory khác.
- **GC time/CPU:** chi phí collector, bao gồm overhead của string dedup khi được bật.
- **String object count:** số objects, có thể **không giảm do dedup**.
- **Backing array count/size:** gần mục tiêu dedup hơn nhưng cần công cụ/heap dump phù hợp để nhìn rõ.

Không thể lấy một lần `Runtime.totalMemory() - freeMemory()` trước/sau và suy ngay hiệu quả dedup: nó chịu ảnh hưởng GC scheduling, class loading, TLAB, JIT, string ages và memory khác.

### 9.1. Quy trình benchmark tối thiểu

1. Chốt JDK vendor/version, GC, `-Xms/-Xmx`, workload và tập dữ liệu.
2. Chạy warm-up đủ và nhiều lần lặp; giữ data còn reachable đến lúc đo.
3. So sánh **G1 baseline** với **G1 + `UseStringDeduplication`** khi các thông số khác giữ nguyên.
4. Nếu đánh giá Compact Strings, đo riêng với `-XX:-CompactStrings`; tránh thay đổi thêm cả GC/heap size trong cùng một thí nghiệm.
5. Đọc GC logs, heap histogram/dump, allocator/CPU metrics phù hợp thay vì dựa trên một lần `System.gc()`.
6. Xác nhận ứng dụng thật có tần suất String trùng lặp đủ cao; synthetic workload chỉ là minh họa.
7. Đo p95/p99 latency và CPU nếu ứng dụng latency-sensitive, vì tiết kiệm heap có thể đổi bằng throughput/CPU.
8. Ghi lại trade-offs và có kế hoạch rollback flags khi triển khai production.

## 10. Các nhầm lẫn thường gặp

1. **“Compact Strings là pooling các chuỗi giống nhau.”** Sai: nó là biểu diễn ký tự gọn hơn **trong mỗi String**, không gộp String objects.
2. **“String dùng UTF-8 nội bộ từ Java 9.”** Sai trong HotSpot JDK 17; JEP 254 dùng LATIN1/UTF16 qua `byte[]` + coder.
3. **“LATIN1 chỉ chứa ASCII 0..127.”** Sai: có thể biểu diễn cả các UTF-16 code units tới `U+00FF`; ví dụ `é`.
4. **“`length()` đếm bytes của internal value.”** Sai: `length()` đếm UTF-16 code units.
5. **“Một emoji luôn có `length() == 1` vì là một ký tự nhìn thấy.”** Sai: ký tự ngoài BMP dùng surrogate pair, thường `length()==2`.
6. **“`getBytes(UTF_8)` sẽ trả backing `byte[] value` của HotSpot.”** Sai: đó là conversion theo requested charset.
7. **“Gọi `intern()` tự biến đối tượng gọi thành cùng reference với object trong pool.”** Sai: caller phải **dùng giá trị trả về**.
8. **“Hai chuỗi có cùng nội dung thì `a == b` luôn true.”** Sai: dùng `equals` để so nội dung.
9. **“Mọi runtime concatenation đều được auto-intern.”** Không có bảo đảm. Literal và string-valued constant expressions là các trường hợp chuẩn.
10. **“Interned strings còn nằm vĩnh viễn ở PermGen trên Java 17.”** Sai: đừng áp layout HotSpot cũ vào HotSpot hiện đại.
11. **“String deduplication gộp các String objects thành một.”** Sai: nó nhắm tới **backing arrays**; object identities giữ nguyên.
12. **“Bật `UseStringDeduplication` bảo đảm mọi trùng lặp được xử lý ngay lập tức.”** Sai: GC selection/timing là bất định.
13. **“Dedup sẽ làm `a == b` từ false thành true.”** Sai: object identity không đổi.
14. **“Dedup mặc định bật trên HotSpot JDK 17 G1.”** Sai theo tài liệu lệnh `java` JDK 17: option mặc định tắt.
15. **“Bật dedup luôn giúp tiết kiệm RAM và tăng tốc.”** Sai: phụ thuộc trùng lặp và CPU/GC overhead.
16. **“Dùng `System.gc()` rồi lập tức đọc kết quả chứng minh dedup hoàn tất.”** Sai: GC là hint, không có bảo đảm dedup xong.
17. **“`new String("abc")` tương đương lấy lại chính literal object.”** Sai: tạo String object riêng; backing data có thể được chia sẻ tùy implementation.
18. **“Nếu byte[] bên trong chia sẻ thì hai Strings phải là cùng object.”** Sai: object identity và backing storage identity khác nhau.
19. **“Đổi `-XX:-CompactStrings` sẽ khiến `equals`/Unicode bị sai.”** Sai: một tối ưu nội bộ không được phá hợp đồng Java API.
20. **“Có thể đo coder bằng `String.getBytes` rồi biết layout thật.”** Sai: encoding result không phải storage inspector.

## 11. Tự kiểm tra có đáp án

**Câu 1.** Compact Strings giúp gì cho một String dài 40 code units hoàn toàn thuộc U+0000..U+00FF?

**Đáp án:** HotSpot có thể dùng LATIN1 backing payload khoảng 40 bytes thay vì UTF16 khoảng 80 bytes; tổng heap object vẫn phải cộng headers/padding.

**Câu 2.** String `"😀"` có `length()` và `codePointCount(0,length())` bằng bao nhiêu?

**Đáp án:** `length() == 2`; code point count bằng `1`.

**Câu 3.** Vì sao String `"café"` có thể dùng LATIN1 trong HotSpot nhưng `getBytes(UTF_8)` dài 5?

**Đáp án:** LATIN1 internal representation và UTF-8 external encoding là hai cách mã hóa khác nhau; `é` là U+00E9 (một LATIN1 byte) nhưng hai UTF-8 bytes.

**Câu 4.** `a.equals(b)==true` nhưng `a==b==false`; sau khi gọi `a.intern()` và `b.intern()`, `a==b` có đổi không?

**Đáp án:** Không. Nếu giữ refs ban đầu thì vẫn false. `a.intern()==b.intern()` mới true theo canonical pool contract.

**Câu 5.** Bật string dedup có làm hai `String` objects trùng content biến thành một object không?

**Đáp án:** Không. HotSpot chỉ có thể cho hai objects riêng chia sẻ backing byte array; object identities không đổi.

**Câu 6.** Nếu ứng dụng có 100.000 Strings nhưng hầu như mọi nội dung đều khác nhau, nên bật `intern()` tràn lan hay không?

**Đáp án:** Không nên mặc định. Ít nội dung trùng nhau thì overhead StringTable/cache có thể lớn hơn lợi ích; cần profiling.

**Câu 7.** Dữ liệu toàn ký tự Hán có được nén LATIN1 bằng Compact Strings không?

**Đáp án:** Không, nếu có code units ngoài U+00FF thì HotSpot sử dụng UTF16 representation theo cơ chế này.

**Câu 8.** Vì sao kết quả stdout `sameObject=false` của `DedupWorkload` vẫn false ngay cả khi GC đã dedup thành công?

**Đáp án:** Vì GC chỉ chia sẻ backing arrays, không gộp hai String objects; `==` so identities.

**Câu 9.** Cờ HotSpot JDK 17 nào bật string dedup trên G1?

**Đáp án:** `-XX:+UseG1GC -XX:+UseStringDeduplication`; có thể thêm `-Xlog:stringdedup*=debug` để xem logs phụ thuộc hoạt động GC.

**Câu 10.** Tại sao không thể chỉ dùng `javap -c` để kết luận một String đang dùng UTF16 backing và đã được dedup?

**Đáp án:** `javap` cho thấy bytecode và constant pool, không hiển thị runtime backing data của từng object hoặc trạng thái GC dedup.

## 12. Tóm tắt ngắn bằng ba câu

**Compact Strings** trả lời: *Một String object đang dùng bao nhiêu bytes để lưu ký tự theo HotSpot internal representation?*

**String interning** trả lời: *Những references do `intern()` trả về có thể trỏ về cùng một canonical String object khi nội dung bằng nhau không?*

**String deduplication** trả lời: *Những String objects riêng biệt đang có thể chia sẻ cùng backing array để giảm heap footprint không?*

```text
                     String nội dung "shared"
                              │
                     ┌────────┴────────┐
                     │                 │
             Compact Strings       Interning
             LATIN1 / UTF16        canonical object
             giảm bytes/array      cho equal content
                     │                 │
                     └────────┬────────┘
                              │
                        GC deduplication
                      (nếu được bật/phù hợp)
                              │
                nhiều String object riêng biệt
                 có thể dùng chung backing data

equals(): nội dung            == : object identity
```

Cả ba cùng có thể mang lại lợi ích, nhưng **chọn đúng công cụ theo đúng vấn đề**: Compact Strings tối ưu **encoding/storage của mỗi value**, interning tối ưu **canonical object reuse**, dedup tối ưu **trùng lặp backing arrays giữa các objects**. Khi tối ưu ứng dụng thật, hãy ưu tiên API semantics, đo memory/GC/CPU trên workload đại diện và chỉ thay cấu hình hoặc code sau khi hiểu rõ lợi ích cùng chi phí.

### Tài liệu tham khảo

- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): biểu diễn String bằng `byte[]` và coder LATIN1/UTF16 (Java 9+).
- [JEP 192 — String Deduplication in G1](https://openjdk.org/jeps/192): mục tiêu chia sẻ backing arrays của equal Strings.
- [Java SE 17 — `String.intern()` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()): canonical reference contract và literals.
- [JLS Java SE 17 — String literals (`3.10.5)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): interned literals/constant expressions.
- [JDK 17 `java` launcher manual — `UseStringDeduplication`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): option G1 và giá trị mặc định.
- [HotSpot/OpenJDK JDK 17 `String.java` source](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java): chi tiết byte[]/coder implementation, không phải public ABI.
- [JDK 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): quan sát bytecode/constant pool.
