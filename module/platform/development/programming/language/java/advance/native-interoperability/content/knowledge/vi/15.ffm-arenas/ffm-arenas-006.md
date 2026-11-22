# Arena và cấp phát: Đóng Arena bằng try-with-resources và xử lý đóng lại hoặc đóng sai luồng

## 1. Vì sao phải quản lý việc đóng Arena?

Trong Java **Foreign Function & Memory (FFM) API**, `Arena` quản lý vòng đời các vùng nhớ (memory regions) và `MemorySegment` được cấp phát từ chúng. Khi cấp phát off-heap memory, không đủ để biết địa chỉ và kích thước: chương trình còn phải biết **khi nào vùng nhớ hợp lệ** và **thread nào được quyền truy cập**.

Ví dụ:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 42);
    System.out.println(segment.get(ValueLayout.JAVA_INT, 0));
}
```

Đây là đoạn minh họa rút gọn; chương trình `ArenaCloseDemo.java` độc lập có ở mục 5. Khi thoát khỏi `try`, Java **tự gọi `arena.close()`**. Nếu đóng thành công, scope của arena hết hiệu lực, các memory segments thuộc scope không còn truy cập được, và các vùng off-heap memory mà arena quản lý được thu hồi.

Có hai tình huống dễ sai đặc biệt:

- **Đóng lại:** `Arena.close()` **không idempotent**. Nếu arena đã được đóng, gọi `close()` lần nữa ném `IllegalStateException`.
- **Đóng sai luồng:** `Arena.ofConfined()` có thread sở hữu. Gọi `close()` từ thread không phải owner ném `WrongThreadException`.

`try-with-resources` giúp thiết lập điểm đóng rõ ràng, nhưng **không vô hiệu hóa hai quy tắc trên**. Cú pháp `try` vẫn có thể gặp lỗi nếu bạn tự đóng trước đó, đóng từ sai thread hoặc thực hiện cleanup trong lúc có tác vụ khác đang dùng bộ nhớ.

Bài dùng các API `Arena.ofConfined()`, `Arena.ofShared()`, `Arena.ofAuto()`, `Arena.global()` thuộc `java.lang.foreign`. Với **JDK 22+**, FFM đã chính thức (JEP 454); với **JDK 21**, FFM là Third Preview (JEP 442) và cần bật `--enable-preview` khi compile/run. Ví dụ sẽ được kiểm thử trực tiếp trên OpenJDK 24, còn lệnh JDK 21 có ghi riêng.

## 2. Arena, Scope và thời gian sống của MemorySegment

`Arena` dùng để cấp phát bộ nhớ và quản lý scope của một nhóm tài nguyên. Một `MemorySegment` dù vẫn còn biến Java trỏ tới nó cũng **không thể sử dụng** sau khi arena của nó đóng thành công.

```text
Tạo Arena.ofConfined()
          │
          ▼
  allocate MemorySegment A, B, ...
          │
  get/set trên owner thread
          │
          ▼
  kết thúc try-with-resources
          │
          ▼
      arena.close()
          │
          ├─ scope().isAlive() == false
          ├─ native memory được arena quản lý giải phóng
          └─ A, B, ... đều bị invalidated
                 │
                 ▼
         get/set sau close
       IllegalStateException
```

Hợp đồng này tạo **temporal safety**: các thao tác Java FFM có kiểm tra trạng thái scope sẽ từ chối truy cập bộ nhớ đã được giải phóng. Nó không có nghĩa bạn có thể bỏ qua lỗi khi tạo native downcall hoặc truyền con trỏ ra thư viện C: thiết kế lifetime phải nhất quán ở cả hai bên.

### Bốn loại Arena phổ biến

| Loại | Tạo bằng | Quyền truy cập segment | Đóng tường minh? | Quy tắc |
| --- | --- | --- | --- | --- |
| **Confined** | `Arena.ofConfined()` | Chỉ owner thread | Có | Chỉ owner thread được đóng |
| **Shared** | `Arena.ofShared()` | Nhiều threads | Có | Bất kỳ thread nào có thể đóng, nhưng cần phối hợp với công việc đang truy cập |
| **Automatic** | `Arena.ofAuto()` | Nhiều threads | **Không** | Bộ nhớ quản lý bởi runtime/GC; không đóng thủ công |
| **Global** | `Arena.global()` | Nhiều threads | **Không** | Vòng đời toàn JVM; không đóng thủ công |

Confined arena thích hợp cho một tác vụ ngắn trên một thread. Shared arena phù hợp khi memory cần nhiều thread cùng dùng, nhưng **không tự đồng bộ dữ liệu** và không tự đợi workers ngừng dùng trước khi close. Auto/global là những loại lifetime khác; không sử dụng `try-with-resources` như cách dọn chúng.

## 3. `try-with-resources` đóng Arena thế nào?

`Arena` là `AutoCloseable`. Mẫu chuẩn:

```java
try (Arena arena = Arena.ofConfined()) {
    // Sử dụng tất cả segments thuộc arena trong phạm vi này.
} // Java tự thực hiện arena.close().
```

Diễn biến:

1. Java tạo resource `arena` trước khi chạy body.
2. Trong body, các `MemorySegment` còn hợp lệ nếu scope alive và thread đúng.
3. Khi thoát body vì chạy xong, `return` hoặc exception, Java **thử gọi `close()`**.
4. Nếu `close()` thành công, scope không còn alive, các segment vô hiệu hóa và memory của arena được giải phóng.
5. Nếu `close()` **tự ném exception**, lời gọi `try-with-resources` cũng có thể thất bại. Cú pháp `try` không bảo đảm việc close luôn thành công khi vi phạm ownership/race.

Tương đương về ý tưởng, có thể quản lý thủ công:

```java
Arena arena = Arena.ofConfined();
try {
    // Công việc...
} finally {
    arena.close();
}
```

Nhưng `try-with-resources` thể hiện rõ ownership và giảm nguy cơ quên `close` trên các đường return/exception. Khi hai resource cùng khai báo trong một `try (...)`, Java đóng chúng theo **thứ tự ngược** với khai báo; nếu body ném exception và close cũng ném thì exception từ close được đính kèm dạng **suppressed exception** cho lỗi chính.

### Lỗi: tự gọi `close()` trong block đã được quản lý

```java
// CỐ Ý SAI: Java sẽ đóng resource thêm lần nữa ở cuối block.
try (Arena arena = Arena.ofConfined()) {
    arena.close(); // Đã đóng thành công lần đầu.
} // Close lần hai -> IllegalStateException.
```

**Cách đúng:** để `try-with-resources` tự đóng. Nếu cần đóng sớm theo ngữ nghĩa nghiệp vụ, hãy thay đổi phạm vi `try` để nó kết thúc sớm; không chủ động double-close. Với API wrapper cần `close()` idempotent, wrapper phải có cơ chế trạng thái/ownership riêng; không dựa vào `Arena.close()` là idempotent.

## 4. Đúng exception khi đóng lại, sai thread, in-flight access

Theo tài liệu `Arena.close()` của JDK 21/22/24, các tình huống quan trọng là:

| Tình huống | Kết quả |
| --- | --- |
| Confined/shared arena đã đóng, gọi `close()` thêm lần nữa | `IllegalStateException` |
| Gọi `close()` trên `Arena.ofConfined()` từ non-owner thread | `WrongThreadException` |
| Truy cập `get()/set()` trên segment sau khi arena đã đóng | `IllegalStateException` |
| Non-owner thread truy cập segment thuộc confined arena | `WrongThreadException` |
| Đóng arena trong lúc segment vẫn đang được truy cập concurrent, chẳng hạn downcall giữ segment | Có thể ném `IllegalStateException` |
| Gọi `close()` trên arena global/automatic không hỗ trợ đóng | `UnsupportedOperationException` |

**Không nhầm `WrongThreadException` với `IllegalThreadStateException`.** `WrongThreadException` (thuộc `java.lang`) biểu thị thao tác FFM vi phạm thread ownership. `IllegalStateException` khi close không nhất thiết là double-close; nó cũng có thể liên quan thao tác bộ nhớ chưa kết thúc.

### Phân biệt đóng thất bại và đóng thành công

Khi một confined arena bị non-owner thread gọi `close()`, lệnh đó **thất bại**. Lệnh thất bại không được coi là đã giải phóng native memory. Trong ví dụ đã kiểm chứng, owner thread thấy `scope().isAlive() == true` và vẫn truy cập segment bình thường trước khi tự đóng.

Với shared arena, nếu concurrent access khiến `close()` thất bại, ứng dụng cần xử lý theo chính sách shutdown phù hợp; không nên nuốt lỗi hay tự coi resource đã đóng. Thiết kế đúng là **ngăn thêm tác vụ mới, đợi công việc đang dùng segment hoàn tất, rồi đóng**.

## 5. Chương trình hoàn chỉnh Java 22+: đóng đúng và chẩn đoán cả hai lỗi

Ví dụ `ArenaCloseDemo.java` dưới đây gồm: truy cập trong/ngoài phạm vi, đóng hai lần, đóng confined arena từ luồng khác, và shared arena truy cập từ luồng phụ. Mọi thread đều có `join()` để stdout theo thứ tự xác định và để shared arena không bị đóng khi worker còn sử dụng.

### 5.1. Tạo tệp `ArenaCloseDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaCloseDemo {
    public static void main(String[] args) throws InterruptedException {
        MemorySegment escaped;
        try (Arena arena = Arena.ofConfined()) {
            escaped = arena.allocate(ValueLayout.JAVA_INT);
            escaped.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("inside: " + escaped.get(ValueLayout.JAVA_INT, 0));
        }
        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("after close: IllegalStateException");
        }

        Arena manual = Arena.ofConfined();
        manual.close();
        try {
            manual.close();
        } catch (IllegalStateException expected) {
            System.out.println("double close: IllegalStateException");
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 7);
            Thread other = new Thread(() -> {
                try {
                    arena.close();
                } catch (WrongThreadException expected) {
                    System.out.println("wrong-thread close: WrongThreadException");
                }
            });
            other.start();
            other.join();
            System.out.println("still alive: " + arena.scope().isAlive());
            System.out.println("owner reads: " + segment.get(ValueLayout.JAVA_INT, 0));
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment segment = shared.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 99);
            Thread reader = new Thread(() ->
                System.out.println("shared read: "
                        + segment.get(ValueLayout.JAVA_INT, 0)));
            reader.start();
            reader.join();
        }
    }
}
```

### 5.2. Compile và run trên JDK 22+

Trong thư mục chứa source:

```bash
java -version
javac -version
mkdir -p out
javac -encoding UTF-8 -d out ArenaCloseDemo.java
java -cp out ArenaCloseDemo
```

**Stdout chính xác, đã biên dịch và chạy trên OpenJDK 24.0.2:**

```text
inside: 42
after close: IllegalStateException
double close: IllegalStateException
wrong-thread close: WrongThreadException
still alive: true
owner reads: 7
shared read: 99
```

### 5.3. Lần theo kết quả

1. `inside: 42` — native segment còn hợp lệ trong block `try`.
2. `after close: IllegalStateException` — Java đã tự close arena khi ra khỏi `try`; giữ reference `escaped` trong Java không làm memory thuộc arena sống lại.
3. `double close: IllegalStateException` — gọi `close()` lần thứ hai trên arena thủ công đã đóng.
4. `wrong-thread close: WrongThreadException` — `other` không phải owner của `Arena.ofConfined()`.
5. `still alive: true` — thất bại khi đóng từ non-owner thread không khiến arena bị đóng.
6. `owner reads: 7` — owner vẫn có thể đọc vùng nhớ còn hợp lệ; ra khỏi block thì chính owner thread tự đóng arena.
7. `shared read: 99` — thread phụ được phép đọc segment từ `Arena.ofShared()`; `reader.join()` bảo đảm thread kết thúc trước khi `try` đóng shared arena.

Ví dụ tránh phụ thuộc vào `Exception.getMessage()`, vì message có thể thay đổi giữa các bản JDK. Các phép thử chỉ đối chiếu **loại exception**, tình trạng scope và giá trị đã ghi.

## 6. Dùng cùng ý tưởng trên JDK 21 preview

FFM trong **JDK 21** là **Third Preview (JEP 442)**. Các API `Arena.ofConfined()`, `Arena.ofShared()` và `scope().isAlive()` đã có, nhưng compiler/JVM JDK 21 yêu cầu bật preview. Dùng lệnh sau với **JDK 21**:

```bash
java -version
javac -version
mkdir -p out

javac --enable-preview --release 21 \
  -encoding UTF-8 -d out ArenaCloseDemo.java

java --enable-preview -cp out ArenaCloseDemo
```

Đừng bỏ `--enable-preview` ở bước `java` chỉ vì `javac` đã chạy thành công. Sang **JDK 22**, FFM đã finalized (JEP 454), không cần `--enable-preview` **chỉ để dùng FFM**. Ví dụ trên được **kiểm tra thực thi với JDK 24**, còn các lệnh JDK 21 được đối chiếu tài liệu API preview, **không khẳng định đã chạy JDK 21 thực tế ở môi trường này**.

Không lấy API incubator `jdk.incubator.foreign` của JDK 17 để thay nguyên văn bằng source `java.lang.foreign` của JDK 21/22. Đây là các giai đoạn API khác nhau.

## 7. Xử lý double-close theo ownership

### 7.1. Một Arena chỉ nên có một owner logic đóng

Một method tạo arena rồi đóng trước khi caller dùng segment là lỗi lifetime:

```java
// MINH HỌA THIẾT KẾ SAI: segment trả ra đã mất hiệu lực.
static MemorySegment invalidReturn() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    }
}
```

Hàm này có thể biên dịch, nhưng `MemorySegment` trả ra không còn dùng được sau khi arena đã đóng. **Java object reference còn tồn tại không có nghĩa vùng native memory vẫn còn hợp lệ.**

Một hợp đồng đúng là xử lý xong trong scope và trả **giá trị Java**:

```java
static int computeValue() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(ValueLayout.JAVA_INT);
        s.set(ValueLayout.JAVA_INT, 0, 123);
        return s.get(ValueLayout.JAVA_INT, 0);
    }
}
```

Nếu cần trả segment cho caller để dùng lâu hơn method tạo ra, phải thiết kế caller sở hữu vòng đời của **cả Arena**, hoặc một wrapper `AutoCloseable` đóng nó đúng một lần. Tránh hai bên tự nhận trách nhiệm `close()`.

### 7.2. `scope().isAlive()` không biến close thành idempotent

Đoạn sau có thể giúp debug, nhưng **không phải giải pháp đồng bộ**:

```java
if (arena.scope().isAlive()) {
    arena.close();
}
```

Trên shared arena, giữa hai dòng đó một thread khác có thể đã đóng; `close` vẫn có thể ném `IllegalStateException`. Đây là **check-then-act race**. Trên confined arena, dù scope alive thì non-owner vẫn không được close. Vì thế cần một owner logic/cơ chế locking chứ không chỉ hỏi `isAlive()`.

### 7.3. Vì sao không nên nuốt `IllegalStateException` vô điều kiện?

Một `catch (IllegalStateException ignored)` quanh `close()` che mất lý do thật: double-close, in-flight memory access hay bug trong lifecycle. Đặc biệt, nếu close thất bại vì công việc native đang dùng segment, tiếp tục chạy như thể memory đã giải phóng có thể làm sự cố khó chẩn đoán hơn. Chỉ thiết kế wrapper idempotent khi API của bạn **thực sự yêu cầu**, và phải giữ ràng buộc thread/callbacks đúng.

## 8. Wrong-thread close: chọn confined hay shared?

### 8.1. Confined: cùng thread tạo, dùng và đóng

Mẫu thích hợp cho một worker thread độc lập:

```java
static void runOnOwnerThread() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(ValueLayout.JAVA_LONG);
        s.set(ValueLayout.JAVA_LONG, 0, 100L);
        // Work và cleanup trên cùng thread đang chạy method.
    }
}
```

`Arena.ofConfined()` có owner ngay khi được tạo. Nếu tạo arena ở main thread rồi chuyển nó sang executor, executor **không trở thành owner**. Cách sửa thường là **đưa cả bước tạo–sử dụng–đóng vào task của executor**, không chỉ chuyển việc gọi `close()`.

Nếu một non-owner thread đã thử close và nhận `WrongThreadException`, **không retry ở chính thread sai**. Đưa cleanup về owner thread hoặc thiết kế sang shared arena nếu thực sự cần nhiều thread.

### 8.2. Shared: thread nào cũng có thể đóng, nhưng phải đợi công việc kết thúc

`Arena.ofShared()` không có owner thread duy nhất. Segment của nó có thể truy cập từ nhiều thread; bất kỳ thread nào cũng có thể gọi `close()`. Tuy vậy **không có nghĩa đóng trong lúc một thread khác đang dùng memory luôn thành công**. Với concurrent access hoặc in-flight downcall sử dụng segment, `close()` có thể ném `IllegalStateException`.

Một chu trình shutdown nên:

1. Ngừng phân phối task mới có dùng segment.
2. Đợi những task đang dùng memory hoàn tất bằng `Future.get()`, `Thread.join()` hoặc lifecycle barrier thích hợp.
3. Chỉ một owner logic chịu trách nhiệm gọi `close()` sau khi không còn in-flight access.
4. Không dùng lại segment sau đóng thành công.

**Cẩn trọng với interrupt:** nếu thread chờ `join()/get()` bị interrupt, điều đó **không đồng nghĩa worker đã dừng**. Khi thoát `try` vì exception, `close()` vẫn được thử gọi và có thể thất bại nếu worker đang dùng segment. Sản phẩm thật cần giao thức cancel/shutdown và chính sách interrupt phù hợp.

Cùng lúc, việc có shared arena **không đồng bộ hóa giá trị**: hai thread cùng ghi/đọc một `MemorySegment` vẫn cần dùng lock hoặc các memory access modes đồng bộ tương ứng để tránh data race.

## 9. Không dùng try-with-resources để đóng ofAuto/global

`Arena.ofAuto()` được runtime quản lý, còn `Arena.global()` có vòng đời gắn với JVM. Hai loại này **không hỗ trợ đóng tường minh**. Nếu đặt chúng vào `try (...)` chỉ vì kiểu `Arena` là `AutoCloseable`, Java vẫn gọi `close()` ở cuối block và nhận `UnsupportedOperationException`.

```java
// CỐ Ý SAI cho mục đích cleanup đúng block:
try (Arena arena = Arena.ofAuto()) {
    MemorySegment s = arena.allocate(ValueLayout.JAVA_BYTE);
} // close() không hỗ trợ: UnsupportedOperationException.
```

Khi muốn giải phóng native memory **tại một điểm rõ ràng**, chọn confined/shared arena có lifetime bounded và close được. Khi thật sự muốn auto/global lifetime, không dùng `close()`; phải hiểu rằng thời điểm thu hồi hoặc lifetime khác với một scoped `try`.

## 10. Exception trong body và exception từ cleanup

Với `try-with-resources`:

- **Body chạy xong, close ném:** close exception được truyền ra caller.
- **Body ném, close cũng ném:** body exception là **primary**, close exception nằm trong `getSuppressed()` của primary.
- **Nhiều resources:** close diễn ra theo thứ tự ngược với khai báo; các ngoại lệ đóng cũng được giữ theo quy tắc suppressed exceptions.

Ví dụ chủ đích tạo double-close **và** primary exception:

```java
try (Arena arena = Arena.ofConfined()) {
    arena.close(); // Đóng sớm, không được khuyến nghị.
    throw new IllegalArgumentException("work failed");
} catch (IllegalArgumentException primary) {
    System.out.println(primary.getMessage());           // work failed
    System.out.println(primary.getSuppressed().length); // 1
}
```

Khi body ném, Java thử tự close lần nữa, làm phát sinh `IllegalStateException`. Java giữ `IllegalArgumentException` làm primary và đưa close exception vào suppressed. Đây chỉ là **đoạn minh họa lỗi**, không phải một phần của chương trình `ArenaCloseDemo` chạy ở mục 5.

Vì thế khi debug một lỗi trong body kèm bất thường cleanup, hãy đọc **cả primary lẫn suppressed exceptions**. Không bỏ exception close hoặc che mất lỗi gốc bằng logging tùy tiện.

## 11. Chẩn đoán những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` khi `close()` lần thứ hai | Đã close trước đó | Một owner đóng đúng một lần; tránh đóng thủ công trong `try-with-resources` |
| `IllegalStateException` khi truy cập segment đã trả ra khỏi method | Arena bên trong method đã hết scope | Trả giá trị Java/copy dữ liệu hoặc chuyển ownership của Arena cho caller |
| `WrongThreadException` khi close confined arena | Không phải owner thread | Đưa cleanup về owner, hoặc chọn shared design có đồng bộ |
| `WrongThreadException` khi `get()/set()` | Segment confined bị truy cập sai luồng | Làm việc trên owner thread hoặc dùng shared arena |
| `IllegalStateException` khi close shared arena trong downcall | Segment đang được dùng | Đợi công việc hoàn tất trước khi đóng |
| `UnsupportedOperationException` khi đóng `ofAuto/global` | Không hỗ trợ explicit close | Đừng dùng `try-with-resources` để đóng loại này |
| `scope().isAlive()` là true nhưng close vẫn thất bại | Sai thread, concurrent access hoặc check-then-act race | Thiết kế ownership và đồng bộ đúng |
| `getSuppressed()` có close error | Body exception và close exception cùng xảy ra | Kiểm tra cả lỗi chính lẫn lỗi cleanup |
| JDK 21 compile báo preview disabled | FFM còn preview trong JDK 21 | `javac --enable-preview --release 21` và `java --enable-preview` |
| JDK 17 báo không có `java.lang.foreign` | FFM đang thuộc incubator API khác | Chọn JDK 22+ hoặc di chuyển source và build phù hợp |

## 12. Checklist và bài tập tự luyện

**Checklist khi triển khai:**

- [ ] Chọn loại `Arena` theo lifetime và yêu cầu multi-thread, không chỉ theo cú pháp cấp phát.
- [ ] Confined arena: cùng thread tạo, sử dụng và đóng.
- [ ] Shared arena: ngừng dispatch và đợi tất cả thao tác đang dùng memory trước khi đóng.
- [ ] Dùng `try-with-resources` cho arena closeable có lifetime rõ ràng.
- [ ] Không gọi `close()` thủ công bên trong một `try (Arena ...)` được Java tự quản lý.
- [ ] Không đóng `ofAuto()/global()`.
- [ ] Không truy cập `MemorySegment` sau khi arena đóng; nếu cần kết quả, copy ra Java trước.
- [ ] Không nuốt `IllegalStateException`/`WrongThreadException` mà không hiểu lifecycle.
- [ ] Khi body có exception, kiểm tra `getSuppressed()` nếu cleanup cũng có thể lỗi.
- [ ] Kiểm tra version: JDK 21 FFM preview cần flags; JDK 22+ FFM finalized.

**Câu hỏi:**

1. Vì sao `try-with-resources` ưu việt hơn đóng arena thủ công trong nhiều method?
2. Trong `ArenaCloseDemo`, vì sao `escaped` vẫn là Java reference nhưng `get` sau block ném `IllegalStateException`?
3. Gọi `close()` hai lần trên cùng confined arena gây lỗi gì? Tại sao `Arena.close()` không idempotent?
4. Nếu thread A tạo `Arena.ofConfined()` và thread B gọi `close()`, exception nào xuất hiện? Owner còn có thể close không?
5. Có thể dùng một segment từ confined arena trên worker thread khác không? Phương án chuyển ownership an toàn là gì?
6. Khi nào `Arena.ofShared()` phù hợp hơn confined? Vì sao vẫn phải `join()/Future.get()` trước khi đóng?
7. `scope().isAlive()` có đủ để tránh double-close khi nhiều threads có thể đóng shared arena không?
8. `Arena.ofAuto()` và `Arena.global()` có thích hợp cho `try-with-resources` để dọn memory đúng block không?
9. Khi body và cleanup cùng ném exception, Java đặt exception thứ hai ở đâu?
10. Nếu dùng JDK 21 thay cho JDK 24, phải sửa những JVM/compiler flags nào?

**Ghi nhớ:** `Arena.close()` **không idempotent** (đóng lại → `IllegalStateException`); `Arena.ofConfined()` **chỉ được đóng trên owner thread** (sai luồng → `WrongThreadException`). `try-with-resources` là cách đóng chuẩn cho confined/shared arena khi lifetime nằm gọn trong một block, nhưng vẫn cần kiểm soát ownership, concurrency và exception khi cleanup.

### Tài liệu chính thức

- [Oracle JDK 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 22 — Foreign Function & Memory package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle JDK 21 — Arena Preview API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 24 — Arena API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java Language Specification, `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se22/html/jls-14.html#jls-14.20.3).
- [OpenJDK JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442).
- [OpenJDK JEP 454 — FFM Final](https://openjdk.org/jeps/454).
