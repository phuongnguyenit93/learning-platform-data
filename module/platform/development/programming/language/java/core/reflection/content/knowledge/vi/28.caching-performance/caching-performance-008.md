# Không chia sẻ khả năng truy cập private ngoài phạm vi cần thiết

## 1. Vấn đề trong reflection và cache

Reflection cho phép chương trình tìm và gọi một thành viên lớp thông qua các đối tượng như `Method`, `Field` hoặc `Constructor`. Theo mặc định, API vẫn tuân thủ các kiểm tra truy cập của Java; các thành viên `private` không đương nhiên được phép gọi từ mọi nơi.

`java.lang.reflect.AccessibleObject` (lớp cha của `Method`, `Field`, `Constructor`) có các thao tác `setAccessible(true)` và `trySetAccessible()` để yêu cầu **bỏ qua một số kiểm tra truy cập ngôn ngữ Java** đối với đối tượng phản chiếu cụ thể, trong giới hạn mà Java Platform Module System (JPMS) cho phép. Khi trạng thái này bật, mã khác **được trao chính đối tượng `Method`/`Field` đó** có thể sử dụng khả năng truy cập mà bên sở hữu đã bật.

Vì thế, trong module **Cache và hiệu năng**, nguyên tắc thực hành là:

> **Chỉ giữ và chia sẻ metadata hoặc khả năng gọi đúng với những nơi thật sự cần. Không đưa đối tượng reflection đã được bật quyền private vào cache dùng chung hoặc API công khai.**

Ví dụ rủi ro: component chẩn đoán được phép truy cập phương thức private của một plugin để kiểm tra nội bộ. Nó gọi `method.trySetAccessible()` rồi lưu `Method` trong `public static Map<String, Method>`. Một component khác lấy được reference này có thể gọi `method.invoke(...)` mà không phải tự thiết lập quyền trên cùng đối tượng. Một cache được đặt tên là “tối ưu hiệu năng” lúc này vô tình trở thành nơi **phân phối quyền truy cập mạnh hơn mức cần thiết**.

Điểm cần phân biệt: quyền kiểm tra truy cập của Java/JPMS không phải cơ chế cô lập chống mọi mã độc chạy trong cùng JVM. Việc kiểm soát API, reference và quyền lookup vẫn quan trọng để bảo toàn **đóng gói**, tránh dùng nhầm và hạn chế năng lực được trao ngoài ý muốn.

## 2. Cơ chế quyền trên `AccessibleObject`

| API hoặc thao tác | Ý nghĩa | Lưu ý bảo toàn phạm vi |
| --- | --- | --- |
| `getDeclaredMethod`, `getDeclaredField` | Tra metadata kể cả thành viên không public được khai báo trực tiếp | Tìm thấy metadata không đồng nghĩa được phép gọi/đọc |
| `Method.invoke`, `Field.get/set` | Thực thi thao tác reflection | Tuân thủ kiểm tra truy cập trừ khi các kiểm tra đó được bỏ qua hợp lệ |
| `canAccess(receiver)` | Kiểm tra có truy cập được qua đối tượng reflection này với receiver thích hợp hay không | Chỉ đọc trạng thái, không mở quyền; `null` cho static member/constructor, instance thật cho instance member |
| `trySetAccessible()` | Cố bật trạng thái bỏ qua kiểm tra truy cập, trả `true` nếu thành công; `false` nếu không thể bật | **Làm thay đổi trạng thái** đối tượng khi thành công |
| `setAccessible(true)` | Yêu cầu bật trạng thái bỏ qua kiểm tra truy cập | Có thể ném `InaccessibleObjectException` nếu JPMS không cho phép |
| `setAccessible(false)` | Tắt trạng thái bỏ qua kiểm tra truy cập trên **đối tượng này** | Không phải cơ chế thu hồi mọi reference/handle đã phát tán |
| `MethodHandles.privateLookupIn` | Tạo `Lookup` có quyền truy cập phù hợp vào lớp đích khi đủ điều kiện | `Lookup` cũng là capability nhạy cảm; không cung cấp cho nơi không cần |

Một `Method` đã bật `setAccessible(true)` vẫn phải đáp ứng những điều kiện khác của phép gọi như receiver đúng lớp, số lượng/kiểu tham số tương thích. Bật accessible **không biến phương thức thành public trong bytecode**, không đổi modifiers và không cho quyền vô hạn với mọi package/module.

Với Java 9+, JPMS giới hạn deep reflection. Nếu package của module đích không được mở phù hợp cho module gọi, `trySetAccessible()` có thể trả `false`, còn `setAccessible(true)` có thể ném `InaccessibleObjectException`. Đừng coi `setAccessible(true)` là cách đi vòng mọi ranh giới module.

### Quyền gắn với đối tượng đã trao

Xét đoạn mã sau (minh họa hành vi cần tránh):

```java
// MÃ MINH HỌA ANTI-PATTERN, KHÔNG CHẠY ĐỘC LẬP:
// Method được tạo ở một thành phần được tin cậy:
Method privateMethod = Target.class.getDeclaredMethod("secret");
privateMethod.setAccessible(true);

// Sai phạm vi: đưa đối tượng đã bật quyền vào registry/cache công khai:
sharedRegistry.put("secretMethod", privateMethod);
```

Sau khi reference `privateMethod` thoát ra ngoài, bên nhận có thể sử dụng khả năng đang gắn trên **reference đó**. Việc “ẩn” field cache bằng `private` không đủ nếu một public getter hoặc callback lại trả thẳng đối tượng `Method`. Tương tự, trả một `MethodHandle` đã được tạo với lookup quyền private cũng trao khả năng gọi mà nó chứa.

## 3. Ví dụ Java 17+: mở quyền cục bộ rồi đóng lại

Ví dụ này cố tình có **hai top-level class** trong cùng một tệp: lớp `Ticket` có phương thức private; tiện ích `ScopedPrivateAccessDemo` thuộc **nest khác**, nên ban đầu không có quyền gọi phương thức private qua reflection. Chạy trên **class path/unnamed module** để việc mở quyền trong ví dụ được chấp nhận.

Lưu vào `ScopedPrivateAccessDemo.java`:

```java
import java.lang.reflect.Method;

public class ScopedPrivateAccessDemo {
    static final class Diagnostics {
        static boolean suffixMatches(Ticket ticket, String expected)
                throws ReflectiveOperationException {
            // Mỗi lần gọi tạo đối tượng Method riêng, không đưa vào cache chung.
            Method method = Ticket.class.getDeclaredMethod("lastFour");

            System.out.println("before=" + method.canAccess(ticket));
            if (!method.trySetAccessible()) {
                throw new IllegalStateException(
                        "Private access is not available");
            }

            try {
                System.out.println("during=" + method.canAccess(ticket));
                String suffix = (String) method.invoke(ticket);

                // Trả một kết quả nghiệp vụ tối thiểu, không trả Method.
                return suffix.equals(expected);
            } finally {
                method.setAccessible(false);
                System.out.println("after=" + method.canAccess(ticket));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ticket ticket = new Ticket("DOC-4821");
        System.out.println("label=" + ticket.publicLabel());
        boolean matched = Diagnostics.suffixMatches(ticket, "4821");
        System.out.println("matched=" + matched);
    }
}

final class Ticket {
    private final String identifier;

    Ticket(String identifier) {
        this.identifier = identifier;
    }

    private String lastFour() {
        return identifier.substring(identifier.length() - 4);
    }

    String publicLabel() {
        return "ticket";
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 ScopedPrivateAccessDemo.java
java ScopedPrivateAccessDemo
```

Stdout dự kiến:

```text
label=ticket
before=false
during=true
after=false
matched=true
```

Giải thích:

1. `method.canAccess(ticket)` ban đầu là `false` vì phương thức `Ticket.lastFour()` là private và code gọi thuộc một nest khác.
2. `trySetAccessible()` được phép trong ví dụ chạy trên class path; đối tượng `Method` cục bộ được bật khả năng gọi.
3. `invoke(ticket)` thực thi phương thức và trả chuỗi. Tiện ích trả **boolean** cho caller; không trả chuỗi nội bộ hoặc `Method`.
4. `finally` tắt accessible flag trên **chính đối tượng `Method` cục bộ** trước khi phương thức kết thúc, kể cả nếu `invoke` ném ngoại lệ.
5. `matched=true` chứng minh kết quả sau cùng là dữ liệu tối thiểu đã chủ đích cung cấp, không phải quyền phản chiếu.

**Giới hạn quan trọng:** ví dụ làm rõ vòng đời cục bộ; không khẳng định `setAccessible(false)` là một cơ chế thu hồi quyền tuyệt đối. Nếu trước đó đã phát tán đối tượng, một bản sao/reference khác hoặc handle độc lập vẫn có thể tồn tại. Cũng không nên bật/tắt accessible flag **trên cùng `Method` được dùng đồng thời bởi nhiều thread**: một thread tắt flag có thể làm thread khác bất ngờ thất bại khi gọi.

Trong ứng dụng thông thường, tốt hơn cả là **không dùng reflection vào private** nếu một phương thức public/package-private thích hợp có thể biểu đạt điều cần làm. Phương thức `publicLabel()` trong ví dụ thể hiện lối truy cập hẹp hơn cho nhu cầu phổ biến.

## 4. Thiết kế cache đúng phạm vi

Tối ưu reflection thường hướng tới giảm chi phí **tra cứu metadata lặp lại**. Nhưng cache càng chia sẻ rộng, càng nhiều code có thể giữ reference đến đối tượng truy cập nhạy cảm.

So sánh các thiết kế:

| Thiết kế | Đánh giá |
| --- | --- |
| Cache toàn cục ánh xạ tên → `Method` đã bật accessible và cho mọi component lấy ra | **Tránh**: phát tán reference được cấp khả năng private |
| Cache metadata của public method để phục vụ các thao tác public | Phù hợp hơn nếu có nhu cầu thực tế và quản lý class loader |
| Cache `Method` private bên trong một helper được tin cậy; chỉ xuất API nghiệp vụ hẹp | Có thể chấp nhận khi thật sự cần hiệu năng, nhưng phải kiểm soát caller, luồng sử dụng và vòng đời cache |
| Tìm private method cục bộ mỗi lần, trả kết quả đã kiểm tra | Đơn giản, dễ kiểm toán; đổi lại chi phí lookup lặp lại |
| Dùng `MethodHandle` quyền private rồi công khai handle ra ngoài | Cũng là phát tán khả năng gọi; không phải giải pháp an toàn tự động |

Nếu phương thức thực sự cần được cache, phạm vi nên là **component sở hữu công việc**, ví dụ:

- Đặt cache ở class/service nội bộ, không có getter trả `Method` hoặc `Lookup`.
- Chỉ trả về giá trị đã giới hạn qua method nghiệp vụ như `boolean matches(...)` hoặc DTO không chứa nội bộ nhạy cảm.
- Không dùng khóa chuỗi tên phương thức một cách mơ hồ; xem xét declaring `Class<?>`, tên, danh sách tham số, static/instance và module/loader khi cần.
- Lựa chọn chính sách eviction/lifecycle phù hợp vì cache giữ `Method`/`Class` lâu có thể giữ tham chiếu đến **class loader của plugin**, làm cản trở việc dỡ phiên bản plugin.
- Dùng cơ chế cache thread-safe (`ConcurrentHashMap`, `ClassValue` khi phù hợp) để tránh thay đổi cấu trúc cache đồng thời; **thread-safe map không biến trạng thái accessible của phần tử thành thread-safe**.

Không nên quyết định cache private reflection chỉ vì “reflection chậm”. Benchmark đúng workload trước; chi phí lookup, invoke, boxing và tạo adapter phụ thuộc JDK, kiểu gọi và tần suất. Nếu logic có thể dùng lời gọi Java trực tiếp, đó thường là đường đơn giản và dễ bảo trì nhất.

### Không bật/tắt quyền trên một đối tượng chia sẻ giữa nhiều thread

Giả sử `Method cached` đã được chia sẻ, một thread làm:

```java
// Thread A — anti-pattern:
cached.setAccessible(true);
try {
    cached.invoke(target);
} finally {
    cached.setAccessible(false);
}
```

Trong lúc đó thread B cũng sử dụng `cached`. Vì flag là trạng thái trên đối tượng reflection, thread B có thể quan sát nó ở những thời điểm không dự kiến. `finally` chỉ bảo đảm thread A **cố đóng sau thao tác**, không tạo một đoạn truy cập nguyên tử cho mọi thread.

Nếu phải dùng private access trong code đồng thời, hãy tránh chia sẻ đối tượng đang bị toggle, cân nhắc tạo đối tượng cục bộ hoặc thiết kế một component sở hữu quyền ổn định và không để capability thoát ra; kiểm tra an toàn luồng và các invariant nghiệp vụ riêng. Khóa đồng bộ chỉ có ý nghĩa nếu **mọi caller** truy cập cùng trạng thái đều dùng đúng khóa, điều mà một reference đã rò rỉ không bảo đảm.

## 5. `MethodHandles.Lookup` cũng là một capability

`MethodHandles.Lookup` đại diện ngữ cảnh truy cập của code tạo ra nó. Đôi khi framework cần `MethodHandles.privateLookupIn(Target.class, callerLookup)` để tạo lookup có quyền cần thiết cho target, nếu điều kiện module/readability/openness được đáp ứng. Sau đó:

```java
// Đoạn minh họa, cần import và điều kiện quyền/module phù hợp:
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(Target.class,
                MethodHandles.lookup());
MethodHandle privateHandle = privateLookup.findVirtual(
        Target.class,
        "hiddenAction",
        MethodType.methodType(void.class));
```

**Không tự biến thành an toàn chỉ vì đã chuyển từ `Method` sang `MethodHandle`**:

- `Lookup` có quyền private nên chỉ đưa vào những đoạn code được tin cậy và cần quyền đó.
- `MethodHandle` trỏ tới private operation cũng trao khả năng gọi; thành phần nhận handle có thể gọi mà không phải tra cứu quyền lại như lúc tạo.
- Không cache private lookup/handle ở registry dùng chung cho những plugin không tin cậy.
- Ưu tiên đóng gói trong helper, chỉ xuất các thao tác đã được kiểm tra và đầu ra được giới hạn.

Java modules vẫn có quyền quyết định package nào mở cho deep reflection. Không dùng `--add-opens` toàn cục chỉ để làm tắt ngoại lệ; thay đổi mở module có thể cấp quyền rộng cho mã khác trong module nhận quyền.

## 6. Thiết kế API thay thế để tránh phải phân phối private access

Một số lựa chọn thường tốt hơn:

**API công khai tối thiểu.** Nếu các bên chỉ cần câu trả lời “mã có hợp lệ không?”, tạo `boolean isValidCode(String input)` thay vì trả `Field` chứa mã.

**Interface dành cho tích hợp.** Plugin cung cấp interface public cho chức năng được phép dùng, thay vì cho host đi tìm member private theo chuỗi tên. Điều này có hợp đồng biên dịch và ít phụ thuộc cấu trúc nội bộ.

**Adapter hoặc service sở hữu quyền.** Nếu framework buộc phải reflection vào private để tương thích legacy, đặt quyền ở một adapter nội bộ; caller truyền yêu cầu đã kiểm tra và chỉ nhận dữ liệu cần thiết.

**Thay thế cho public API và cache metadata.** Đối với phương thức public ổn định, nếu cần, giữ metadata trong cache riêng mà không bật accessible. Vẫn nên xem xét loader lifecycle.

**Module openness ở mức tối thiểu.** Khi plugin là named module, chỉ mở package cần thiết tới module chẩn đoán cụ thể (`opens package.to.inspect to module.diagnostics;`) thay vì `open module` hoặc `--add-opens ...=ALL-UNNAMED` trên toàn bộ ứng dụng. “Mở package” là quyền **ở cấp package/module**, không giới hạn riêng một hàm; vì thế càng cần kiểm soát API component nhận quyền.

## 7. Kiểm tra và xử lý ngoại lệ

Các vấn đề phổ biến khi xây capability nội bộ:

| Tình huống | Nguyên nhân/cách xử lý |
| --- | --- |
| `getDeclaredMethod` ném `NoSuchMethodException` | Kiểm tra đúng tên và danh sách kiểu tham số (primitive khác wrapper), overload và bản class đang nạp |
| `trySetAccessible()` trả `false` | JPMS hoặc quy tắc truy cập không cho phép; từ chối hành động và sửa cấu hình module theo quyền cần thiết |
| `setAccessible(true)` ném `InaccessibleObjectException` | Đích không mở package phù hợp; không retry mù quáng hoặc mở cả module |
| `Method.invoke` ném `IllegalAccessException` | Access check còn hiệu lực hoặc context không đủ quyền; không giả định mở quyền đã thành công |
| `InvocationTargetException` | Mã đích thực sự ném ngoại lệ; xem `getCause()` để chẩn đoán, không đổ lỗi cho accessibility |
| `IllegalArgumentException` khi invoke | Receiver hoặc số/kiểu đối số sai; mở quyền không khắc phục |
| Sau khi unload plugin, class loader vẫn còn tham chiếu | Kiểm tra cache chứa `Class`, `Method`, `Lookup`, handle hay lambda liên quan plugin |
| Test chạy được trên class path nhưng lỗi trên module path | Kiểm tra `opens`, `exports`, module caller/target và class loader |

Không ghi secret, token hay toàn bộ đối số private vào log khi reflection thất bại. Chỉ ghi đủ loại exception, member signature, defining class, module/loader và bước thất bại theo quy tắc bảo vệ dữ liệu của ứng dụng.

## 8. Checklist review dành cho cache reflection

Trước khi cho một cache/reflection helper vào production, kiểm tra:

1. Thành viên private có thật sự cần truy cập không? Có API public/package-private rõ ràng hơn không?
2. Caller nào được gọi helper? Có kiểm tra điều kiện nghiệp vụ trước khi mở quyền?
3. Có đối tượng `Method`/`Field`, `Lookup` hoặc `MethodHandle` nhạy cảm nào thoát ra qua getter, callback, map, event, log hay object được trả về không?
4. Cache nằm đúng nơi sở hữu quyền, hay đang được chia sẻ cho toàn ứng dụng/plugin?
5. Nếu một đối tượng accessible có thể dùng đồng thời, code có dựa vào thao tác bật/tắt flag dễ tranh chấp không?
6. Cache có vòng đời phù hợp với class loader/redeploy/hot reload không?
7. Quyền module có thật sự chỉ mở những package/module cần thiết không?
8. Có test cả trường hợp được phép và từ chối truy cập, sai receiver/đối số, và ngoại lệ từ target không?
9. Đã đo hiệu năng trước khi đánh đổi phạm vi cache lấy tốc độ chưa?

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Nếu một method private được bật `trySetAccessible()`, rồi `Method` đó đưa vào cache công khai, rủi ro chính là gì?

**Đáp án:** Các thành phần lấy được **reference tới chính `Method` đã bật quyền** có thể sử dụng capability truy cập private đó; biện pháp là giữ nó trong component đáng tin cậy và chỉ xuất API nghiệp vụ hẹp.

**Câu 2.** Gọi `setAccessible(false)` trên Method cục bộ có giúp thu hồi mọi handle đã phát tán không?

**Đáp án:** Không. Nó chỉ chỉnh flag trên đối tượng reflection tương ứng, không vô hiệu hóa các capability độc lập khác hoặc xóa mọi reference đã trao.

**Câu 3.** Vì sao dùng `ConcurrentHashMap` không giải quyết toàn bộ rủi ro?

**Đáp án:** Map thread-safe chỉ bảo vệ thao tác map; giá trị `Method` bên trong vẫn có accessible flag riêng và có thể bị thay đổi đồng thời.

**Câu 4.** `MethodHandles.privateLookupIn` có thay được quản lý phạm vi quyền không?

**Đáp án:** Không. `Lookup` và các private handle được tạo ra cũng mang capability; chỉ trao trong phạm vi cần thiết.

**Câu 5.** Có nên bật `--add-opens ...=ALL-UNNAMED` mỗi khi reflection bị từ chối?

**Đáp án:** Không. Trước hết phải xác định ai cần truy cập, package nào cần mở và liệu API public/adapter có giải quyết được không.

**Ghi nhớ:** **Cache metadata để tiết kiệm công tra cứu, nhưng giữ capability truy cập private ở đúng nơi sở hữu và đúng thời hạn.** Với reflection, quyền nằm cả ở **cách tạo đối tượng**, **trạng thái accessible** và **reference bạn trao cho mã khác**; tối ưu hiệu năng không được làm mở rộng phạm vi truy cập ngoài nhu cầu.

Tham khảo: [`AccessibleObject` Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).