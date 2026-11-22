# Di chuyển API cũ sang generics theo từng ranh giới

## Mục tiêu và bối cảnh

Một hệ thống Java lâu năm có thể chứa những API được viết trước khi generics xuất hiện trong Java 5: phương thức trả `List` không có đối số kiểu, nhận `Collection` dạng thô, hoặc nhận và trả `Object`. Các API ấy vẫn chạy, nhưng compiler không thể bảo đảm phần tử được sử dụng đúng loại dữ liệu. Mục tiêu khi di trú là **đưa thông tin kiểu và kiểm tra dữ liệu vào đúng điểm chuyển giao giữa mã cũ và mã mới**, rồi mở rộng phạm vi mã an toàn theo từng bước.

Sau bài này, bạn có thể:

- Xác định **ranh giới** (boundary) giữa thư viện/mô-đun legacy và phần ứng dụng đang dùng generics.
- Chọn cách thay `List` bằng `List<?>`, `List<T>`, `List<User>` hoặc wrapper/adapter đúng mục đích.
- Tạo một **adapter typed** nhận dữ liệu raw, kiểm tra từng phần tử, trả kết quả `List<User>` không chia sẻ trạng thái sửa đổi với tập dữ liệu cũ.
- Bọc API kiểu `Object` bằng `Class<T>` khi cần kiểm tra kiểu lúc chạy.
- Biết cảnh báo `rawtypes` và `unchecked` nên được khoanh vùng ở đâu và khi nào một cast không đủ để bảo đảm an toàn.
- Lập thứ tự di trú theo từng phạm vi cùng chiến lược kiểm tra tương thích source, binary và hành vi.

Bài tập trung vào **chiến lược di trú theo ranh giới**, không yêu cầu viết lại toàn bộ hệ thống cùng lúc. Các ví dụ sử dụng Java 17 trở lên và được biên dịch, chạy để kiểm tra output.

## 1. Vì sao không nên đổi toàn bộ raw type bằng tìm và thay thế?

Xét một API cũ:

```java
interface LegacyRepository {
    java.util.List findAll();
    void save(Object value);
}
```

Chương trình mới muốn làm việc với `User` thay vì mọi `Object`. Có thể nảy sinh ý định sửa trực tiếp thành:

```java
interface UserRepository {
    java.util.List<User> findAll();
    void save(User user);
}
```

Hai khai báo là **minh họa hợp đồng**, phải có lớp `User` để biên dịch độc lập. Đây là hai API khác nhau về cam kết dữ liệu và kiểu tham số của `save`; không thể mặc nhiên coi việc đổi chữ ký là an toàn cho mọi caller.

Những rủi ro trước khi thay:

- Dữ liệu thật do `LegacyRepository.findAll()` trả về có thể gồm `User`, kiểu dữ liệu cũ khác, thậm chí `null`.
- Mã cũ có thể gọi `save(Object)` với các loại đối tượng khác `User`; đổi thành `save(User)` sẽ ảnh hưởng source compatibility.
- Các implementation và module đã biên dịch có thể dựa vào descriptor cũ; với `save(Object)` đổi sang `save(User)`, **descriptor thay đổi**, cần kiểm tra binary compatibility.
- Nếu chỉ thực hiện `(List<User>) legacy.findAll()`, cast không kiểm tra từng phần tử của danh sách vì **type erasure**.
- Một collection mà mã cũ vẫn giữ quyền ghi có thể bị sửa sau thời điểm cast, phá giả định của phần mã mới.

Điểm xuất phát tốt hơn là xác định: **đầu vào nào chưa đáng tin về kiểu, dữ liệu có thể bị ai sửa, và hợp đồng mới cần bảo đảm điều gì**.

## 2. Ranh giới là gì? Nhìn theo hướng di chuyển dữ liệu

Một ranh giới xuất hiện tại điểm một giá trị đi từ vùng thiếu kiểm soát kiểu sang vùng có hợp đồng generic rõ ràng.

```text
        Mã/thư viện legacy
        (raw List, Object, dữ liệu hỗn hợp)
                 |
                 v
       Ranh giới chuyển đổi
       - kiểm tra phần tử
       - đổi biểu diễn nếu cần
       - sao chép/tách quyền sửa
       - báo lỗi có ngữ cảnh
                 |
                 v
          API có generics
       (List<User>, UserRepository)
                 |
                 v
           Business logic
       (chỉ cần dùng User)
```

Một chương trình có thể có nhiều ranh giới: thư viện bên thứ ba, driver cũ, API import dữ liệu, callback, hàng đợi hoặc API trả về `Object`. **Di trú từng ranh giới** nghĩa là hoàn thiện kiểm tra và hợp đồng cho một đường dữ liệu trước, để các lớp sử dụng phía sau không tiếp tục đoán/cast rải rác.

Khi xác định ranh giới, ghi lại:

| Câu hỏi | Điều cần biết |
| --- | --- |
| Ai sở hữu API cũ? | Có thể sửa source hay chỉ có thể viết adapter? |
| Dữ liệu thực gồm những loại nào? | Một kiểu duy nhất, nhiều kiểu hay không rõ schema? |
| Có cho phép `null` không? | Cần giữ, loại bỏ hoặc từ chối `null` rõ ràng |
| Collection có thể bị sửa sau khi trả về? | Nếu có, cần xem xét bản sao/snapshot |
| Caller cần đọc hay ghi? | Đọc có thể dùng wildcard; ghi cần hợp đồng cụ thể |
| Khi dữ liệu sai, xử lý thế nào? | Fail-fast, báo lỗi kèm vị trí, hay thu thập lỗi |
| Có caller/binary cũ không? | Cần adapter song song, migration plan hoặc kiểm tra tương thích |

Việc bắt đầu từ **dữ liệu và hợp đồng** trước khi sửa cú pháp giúp tránh cảnh báo đã biến mất nhưng nguy cơ runtime vẫn còn.

## 3. Kiểu raw, kiểu wildcard và kiểu typed ở hai phía ranh giới

Ba cách khai báo sau không tương đương:

```java
java.util.List raw = obtainLegacyList();
java.util.List<?> unknown = raw;
java.util.List<User> users = convertAndCheck(unknown);
```

Đây là mã **minh họa luồng chuyển đổi**: `obtainLegacyList()` và `convertAndCheck(...)` tượng trưng các phương thức do ứng dụng cung cấp, còn `User` là kiểu nghiệp vụ.

- **`List`**: raw type, bỏ đối số generic. Có thể gọi `add(...)` qua tham chiếu raw với cảnh báo unchecked.
- **`List<?>`**: danh sách có kiểu phần tử chưa biết; an toàn để duyệt dưới dạng `Object` và hạn chế việc đưa giá trị không phải `null` vào.
- **`List<User>`**: lời hứa mà compiler hiểu là mỗi phần tử được trả về dưới dạng `User`. Muốn xây lời hứa này từ nguồn raw, phải có cơ sở kiểm tra thực sự.

Nếu nhiệm vụ chỉ là hiển thị phần tử, `List<?>` có thể là đích cuối của việc cải thiện API:

```java
static void printAnything(java.util.List<?> input) {
    for (Object value : input) {
        System.out.println(value);
    }
}
```

Đoạn trên là phương thức đặt trong một lớp Java. Nó không phải `List<Object>`: Java generics bất biến, `List<String>` **không** tự chuyển thành `List<Object>`. Dùng `List<Object>` khi API cần một danh sách mà hợp đồng chủ động cho phép chứa nhiều loại `Object`; dùng `List<?>` khi chưa biết loại phần tử và chủ yếu cần **đọc**.

## 4. Ví dụ hoàn chỉnh: adapter kiểm tra từng phần tử trước khi trả API typed

Giả sử bạn có `LegacyDirectory` nhận `Object` và trả raw `List`; không thể sửa thư viện đó trong giai đoạn đầu. Mã mới muốn làm việc với `UserDirectory.users(): List<User>`. Ta xây **adapter** nằm giữa.

Tạo tệp **`MigrationBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class MigrationBoundaryDemo {
    // Giả lập thư viện cũ: không được sửa hoặc chưa thể đổi API.
    static final class LegacyDirectory {
        private final List entries = new ArrayList();

        void add(Object entry) {
            entries.add(entry);
        }

        List findAll() {
            return entries;
        }
    }

    record User(String id, String name) {
        User {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
        }
    }

    interface UserDirectory {
        List<User> users();
    }

    static List<User> checkedUsers(List<?> source) {
        Objects.requireNonNull(source);
        List<User> result = new ArrayList<>();

        for (int index = 0; index < source.size(); index++) {
            Object item = source.get(index);
            if (!(item instanceof User user)) {
                String type = item == null
                        ? "null"
                        : item.getClass().getName();
                throw new IllegalArgumentException(
                        "Unexpected entry at index " + index + ": " + type);
            }
            result.add(user);
        }
        return List.copyOf(result);
    }

    static final class LegacyDirectoryAdapter implements UserDirectory {
        private final LegacyDirectory legacy;

        LegacyDirectoryAdapter(LegacyDirectory legacy) {
            this.legacy = Objects.requireNonNull(legacy);
        }

        @Override
        public List<User> users() {
            return checkedUsers(legacy.findAll());
        }
    }

    public static void main(String[] args) {
        LegacyDirectory old = new LegacyDirectory();
        old.add(new User("u1", "Lan"));
        old.add(new User("u2", "Minh"));

        UserDirectory directory = new LegacyDirectoryAdapter(old);
        List<User> snapshot = directory.users();
        System.out.println("users: " + snapshot);

        old.add("wrong format");
        try {
            directory.users();
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("previous snapshot size: " + snapshot.size());
    }
}
```

Từ thư mục chứa tệp:

```bash
javac -Xlint:rawtypes -Xlint:unchecked MigrationBoundaryDemo.java
java MigrationBoundaryDemo
```

**Stdout đã kiểm chứng trên Java:**

```text
users: [User[id=u1, name=Lan], User[id=u2, name=Minh]]
rejected: Unexpected entry at index 2: java.lang.String
previous snapshot size: 2
```

Các cảnh báo compiler được dự kiến ở vùng `LegacyDirectory` do dùng raw `List`, raw `ArrayList` và `entries.add(entry)`. Chúng xuất hiện trong đầu ra của `javac`, không phải stdout của lệnh `java`.

### Giải thích theo từng lớp

**`LegacyDirectory`:** giữ API cũ, cho phép lưu các `Object`. Trong ứng dụng thực tế, đó có thể là lớp trong JAR bên ngoài hoặc nguồn đã triển khai ở nhiều hệ thống. Không đưa `@SuppressWarnings` vào mẫu để người học nhìn rõ cảnh báo.

**`User`:** dùng `record` Java 17 và từ chối field `null`. Điều này làm cho `List<User>` ở phía hiện đại có một kiểu domain rõ ràng.

**`checkedUsers(List<?>)`:** nhận danh sách chưa biết kiểu phần tử. Từng đối tượng được kiểm tra `instanceof User`. Giá trị sai được từ chối bằng lỗi có **vị trí** và **kiểu thực tế**; `null` cũng bị từ chối. Vì mọi phần tử đã qua kiểm tra, phương thức có thể đưa các `User` ấy vào `ArrayList<User>` mà không cần unchecked cast.

**`List.copyOf(result)`:** tạo danh sách không thể sửa qua API thông thường và tách khỏi list đầu vào. Vì `User` là record chỉ giữ `String` bất biến, mẫu ví dụ có một snapshot phù hợp; với một phần tử domain có state mutable, việc copy list không tự biến mọi phần tử thành immutable.

**`LegacyDirectoryAdapter`:** là điểm duy nhất mã mới cần biết đến `LegacyDirectory`. Caller sử dụng `UserDirectory` và không thấy raw `List`.

**Lời gọi thứ hai:** sau khi thư viện cũ thêm một `String` không hợp đồng, lần gọi adapter tiếp theo phát hiện ngay ở index 2. Danh sách `snapshot` đã trả trước đó không bị thêm phần tử vì đã tách dữ liệu.

Ví dụ cố ý viết API cũ và adapter trong cùng một tệp để chạy dễ dàng; ở hệ thống thực, thư viện cũ và adapter thường ở các package/module khác nhau.

## 5. Vì sao không cast thẳng `List` thành `List<User>`?

Một “sửa nhanh” nguy hiểm:

```java
// Ví dụ cần ngữ cảnh có legacyDirectory và lớp User.
// @SuppressWarnings("unchecked")
// List<User> users = (List<User>) legacyDirectory.findAll();
```

Nếu bỏ suppression, compiler thường báo **unchecked cast**. Lý do: do erasure, JVM biết đối tượng là một `List`, nhưng không xác minh được **mọi phần tử** là `User`. Việc cast có thể hoàn tất mà chưa phát hiện một `String` nằm trong danh sách.

Lỗi thường đến sau đó:

```java
// for (User user : users) {
//     System.out.println(user.name()); // Có thể ClassCastException.
// }
```

Trong vòng lặp trên, trình biên dịch có thể sinh cast khi đọc từng phần tử theo giả định `User`. Đây là một dạng **heap pollution**: thực trạng dữ liệu trong đối tượng collection không còn khớp với kiểu generic mà biến đang hứa.

**Kiểm tra từng phần tử rồi tạo list mới** phù hợp khi miền dữ liệu nhỏ, cần type safety và hợp đồng rõ. Nếu dữ liệu rất lớn hoặc streaming, có thể thiết kế validator xử lý từng record, thu thập lỗi/đẩy sang pipeline, hoặc cung cấp view typed có kiểm tra khi đọc; lựa chọn phải làm rõ thời điểm phát hiện lỗi và quyền thay đổi dữ liệu.

Cũng không thể cho rằng:

```java
if (candidate instanceof List<?>) {
    // candidate là List, chưa có bằng chứng tất cả phần tử là User.
}
```

là đủ để trả `List<User>`. `instanceof List<?>` chỉ kiểm tra **kiểu collection ở runtime**; thông tin `User` là đối số kiểu không tồn tại dưới dạng một runtime class `List<User>` chuyên biệt.

## 6. Ranh giới cho API trả `Object`: dùng type token khi thích hợp

Không phải API cũ nào cũng trả collection. Một hệ thống cấu hình có thể dùng `Object read(String key)`, `void write(String key, Object value)`. Mã mới muốn đọc một giá trị cụ thể và phát hiện sai kiểu ngay tại cửa ngõ.

Tạo tệp **`TypedGatewayDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class TypedGatewayDemo {
    static final class LegacySettings {
        private final Map<String, Object> values = new HashMap<>();

        Object read(String key) {
            return values.get(key);
        }

        void write(String key, Object value) {
            values.put(key, value);
        }
    }

    static final class SettingsGateway {
        private final LegacySettings legacy;

        SettingsGateway(LegacySettings legacy) {
            this.legacy = Objects.requireNonNull(legacy);
        }

        <T> T read(String key, Class<T> type) {
            Objects.requireNonNull(type);
            return type.cast(legacy.read(key));
        }

        <T> void write(String key, Class<T> type, T value) {
            Objects.requireNonNull(type);
            legacy.write(key, type.cast(value));
        }
    }

    public static void main(String[] args) {
        LegacySettings old = new LegacySettings();
        SettingsGateway gateway = new SettingsGateway(old);

        gateway.write("retries", Integer.class, 3);
        Integer retries = gateway.read("retries", Integer.class);
        System.out.println("retries: " + retries);

        old.write("retries", "three");
        try {
            gateway.read("retries", Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("rejected: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TypedGatewayDemo.java
java TypedGatewayDemo
```

**Stdout đã kiểm chứng:**

```text
retries: 3
rejected: ClassCastException
```

Phân tích:

- Adapter nhận `Class<T>` tường minh, ví dụ `Integer.class`.
- `Class.cast(Object)` thực hiện **kiểm tra kiểu tại runtime**. Khi giá trị thật là `String` nhưng caller yêu cầu `Integer`, lỗi xảy ra tại ranh giới adapter.
- Generic `<T> T read(...)` cho phép caller nhận kết quả typed, còn token quyết định việc kiểm tra lúc chạy.
- `Class.cast(null)` trả về `null`, nên trong API thật cần định nghĩa rõ quy tắc cho key thiếu/giá trị `null` (ví dụ trả `Optional<T>` hoặc ném ngoại lệ).
- `Class<T>` mô tả được kiểu runtime như `Integer` nhưng **không kiểm tra đầy đủ kiểu lồng nhau** `List<String>` chỉ nhờ `List.class`. Nếu API trả `List` bất kỳ, vẫn phải kiểm tra từng phần tử hoặc dùng biểu diễn type metadata phong phú hơn.

Mẫu này minh họa cách dùng generic method tại **một boundary** mà không buộc phải sửa chữ ký và dữ liệu của `LegacySettings`.

## 7. Di trú dần một API: trước, trong và sau

Hãy hình dung ba giai đoạn cùng tồn tại thay vì một thay đổi toàn cục.

| Giai đoạn | Bên legacy | Ranh giới | Bên consumer mới |
| --- | --- | --- | --- |
| Trước khi di trú | `List findAll()` | Chưa có | Cast rải rác, có nguy cơ lỗi muộn |
| Bước trung gian | Giữ API legacy | `checkedUsers(List<?>)` + `UserDirectory` | Chỉ dùng `List<User>` |
| Khi làm chủ được API nguồn | Có thể đưa generic vào lớp nội bộ theo hợp đồng thật | Adapter còn phục vụ caller cũ hoặc được thu gọn | Dữ liệu typed xuyên suốt |

**Bước 1 — Lập bản đồ caller/callee.** Xác định phương thức cũ, nơi tạo dữ liệu, nơi nhận và sửa collection. Đặc biệt phân biệt **quyền sở hữu** collection: một phương thức trả raw `List` được backing bởi state mutable sẽ khác phương thức trả snapshot.

**Bước 2 — Viết hợp đồng kiểu đích.** Chọn `User`, `List<User>` hoặc `List<?>` đúng với dữ liệu thật. Quyết định `null`, phần tử sai kiểu và hành vi báo lỗi. Không tự suy luận rằng mọi record cũ đều cùng loại.

**Bước 3 — Tạo điểm kiểm tra nhỏ.** Viết adapter chấp nhận raw API nhưng chỉ công bố typed API sau khi dữ liệu được xác minh. Có thể bắt lỗi bằng exception có ngữ cảnh hoặc trả danh sách các lỗi validation; lựa chọn theo nhu cầu nghiệp vụ.

**Bước 4 — Chuyển một nhóm caller sang typed interface.** Thay lời gọi và cast rải rác bằng dependency tới `UserDirectory`. Giữ vùng truy cập API cũ tập trung trong adapter.

**Bước 5 — Kiểm tra với cả dữ liệu đúng lẫn sai.** Dữ liệu trộn kiểu, `null`, danh sách rỗng, đổi dữ liệu sau khi trả về và khả năng concurrent mutation là các điều kiện quan trọng.

**Bước 6 — Di trú nguồn khi có quyền sở hữu.** Khi kiểm chứng được mọi nơi ghi và đọc, thay raw declarations bằng generic cụ thể ở lớp sở hữu dữ liệu; đánh giá ảnh hưởng đến các consumer cũ, subclass/interface và class file.

**Bước 7 — Thu hẹp vùng legacy.** Gỡ những adapter không còn cần khi tất cả caller chuyển xong; giữ adapter làm lớp tương thích nếu hệ thống vẫn phụ thuộc API trước đây.

Các giai đoạn phải có điểm kiểm tra và phạm vi rõ; việc đổi các hàng trăm khai báo `List` thành `List<User>` bằng replace sẽ khó phân biệt cải thiện thực sự với unchecked cast che lỗi.

## 8. Tính tương thích của chữ ký generic không chỉ là cú pháp

Java generics dùng **type erasure**, nên việc tham số hóa một số chữ ký có thể giữ nguyên JVM descriptor. Ví dụ:

```java
// Dạng cũ:
java.util.List findAll();

// Dạng khai báo generic:
java.util.List<User> findAll();
```

Hai khai báo trên có **cùng descriptor kiểu trả về** `()Ljava/util/List;` sau erasure. Nhưng không được kết luận từ đây rằng mọi thay đổi từ raw sang generic đều hoàn toàn tương thích ở mọi chiều:

- **Binary compatibility:** cần kiểm tra descriptor của từng method, tên, visibility, các quan hệ kế thừa/bridge và class đã biên dịch sẵn. Ví dụ đổi `save(Object)` thành `save(User)` thay descriptor từ `(Ljava/lang/Object;)V` sang `(L.../User;)V` và có thể khiến caller binary cũ không liên kết đúng.
- **Source compatibility:** code cũ có thể biên dịch với cảnh báo khi truyền raw type cho API typed, nhưng cũng có những thay đổi gây lỗi biên dịch do các quy tắc generic, wildcard, overload hoặc name clash.
- **Behavioral compatibility:** đổi kiểu khai báo không tự lọc hay chuyển dữ liệu đã lưu. Adapter có thể chủ động báo lỗi khi dữ liệu sai; thay đổi này phải được thống nhất trong hợp đồng.
- **Reflection compatibility:** framework đọc generic `Signature`, tên method hoặc annotation có thể quan sát khác biệt về metadata dù erased descriptor giống nhau.
- **Subclass/interface compatibility:** các phương thức generic có thể khiến compiler tạo **bridge method** khi override; cần biên dịch và kiểm tra theo quan hệ kế thừa thực tế.

Có thể tự quan sát một phần từ tệp `MigrationBoundaryDemo.java` đã biên dịch:

```bash
javap -s -p 'MigrationBoundaryDemo$LegacyDirectory'
javap -s -p 'MigrationBoundaryDemo$LegacyDirectoryAdapter'
```

Đoạn tiêu biểu từ kết quả đã kiểm tra:

```text
java.util.List findAll();
  descriptor: ()Ljava/util/List;

public java.util.List<MigrationBoundaryDemo$User> users();
  descriptor: ()Ljava/util/List;
```

Hai phương thức mang **tên khác nhau**, nên không thể coi chúng là hai phiên bản nhị phân của cùng một method; trích đoạn chỉ chứng minh **raw `List` và `List<User>` đều có return descriptor `Ljava/util/List;`**. Với một hệ thống thật, muốn xác nhận binary compatibility phải so sánh toàn bộ API hiện tại với bản đề xuất, bao gồm method name, tham số và hierarchy.

Tương tự, chạy:

```bash
javap -s -p 'TypedGatewayDemo$SettingsGateway'
```

cho thấy phương thức generic `<T> T read(String, Class<T>)` có dạng erased `(String, Class)Object`. Đây là lý do compiler vẫn phải dựa vào kiểm tra kiểu generic ở source cùng token `Class<T>` tại runtime.

## 9. Chọn chữ ký phù hợp theo hướng dữ liệu

Khi sửa API công khai, hãy quyết định tham số là **nguồn để đọc** hay **đích để ghi**. Wildcard không phải cách trang trí, mà thể hiện ràng buộc kiểu.

**Đọc phần tử như một kiểu cha** (*producer*):

```java
static double sumNumbers(java.util.List<? extends Number> source) {
    double sum = 0;
    for (Number number : source) {
        sum += number.doubleValue();
    }
    return sum;
}
```

Có thể truyền `List<Integer>`, `List<Double>` hoặc `List<Number>`; compiler không cho thêm `Number` tùy ý vào một nguồn có thể là `List<Integer>`. Phương thức là đoạn mã hoàn chỉnh về hành vi, cần đặt trong một class để chạy.

**Ghi một kiểu vào đích chấp nhận kiểu cha** (*consumer*):

```java
static void addLabels(java.util.List<? super String> target) {
    target.add("migrated");
    target.add("validated");
}
```

Có thể truyền `List<String>` hoặc `List<Object>`, vì cả hai có thể nhận `String`. Khi đọc từ `List<? super String>`, chỉ có thể bảo đảm kết quả dưới dạng `Object`.

Quy tắc **PECS** (Producer Extends, Consumer Super) có ích khi làm sạch API legacy có nhiều caller. Không cần thay mọi tham số thành `List<T>`: nếu method chỉ đọc, `List<?>` hoặc `List<? extends T>` thường thể hiện ý định rõ hơn; nếu ghi, hãy chỉ ra kiểu dữ liệu được phép ghi và cân nhắc `? super T`.

Đối với collection hỗn hợp từ nguồn cũ, một typed API như `List<User>` chỉ hợp lệ sau khi có bằng chứng về phần tử. PECS giúp diễn đạt hướng dùng dữ liệu, **không tự xác thực dữ liệu bên trong raw collection**.

## 10. Cảnh báo compiler: theo dõi có chủ đích khi di trú

Trong lúc chạy lệnh:

```bash
javac -Xlint:rawtypes -Xlint:unchecked MigrationBoundaryDemo.java
```

Compiler đã cảnh báo raw `List`, raw `ArrayList` và unchecked `entries.add(entry)` trong phần giả lập legacy. Hai nhóm cần đọc riêng:

| Nhóm cảnh báo | Ý nghĩa | Hành động ưu tiên |
| --- | --- | --- |
| `rawtypes` | Khai báo/tên generic bị dùng không có đối số kiểu | Thay bằng kiểu tham số hóa hoặc wildcard nếu biết hợp đồng |
| `unchecked` | Lời gọi/chuyển kiểu không được kiểm tra đầy đủ | Xác định nguồn dữ liệu, thêm bước xác minh hoặc giới hạn cast có chứng minh |

Trong ví dụ adapter `checkedUsers`, việc nhận `List<?>` và duyệt `Object` không tự tạo unchecked cast. Cảnh báo được giữ lại tại lớp cũ để **xác định chính xác khoản nợ kiểu** chứ không phân tán nó vào `UserDirectory`.

Nếu bạn sở hữu mã nguồn legacy, có thể loại bỏ cảnh báo từng điểm bằng cách thay raw field, constructor và method với generic đúng bản chất. Nếu mã cũ thuộc thư viện bên ngoài, không cần ép thư viện bên ngoài thay đổi ngay: ưu tiên một boundary typed đã kiểm tra.

Chỉ dùng `@SuppressWarnings("unchecked")` sau khi có lập luận tin cậy chứng minh tính đúng kiểu; đặt ở phạm vi nhỏ nhất có thể, kèm lý do và bài kiểm tra phù hợp. **Không dùng suppression như bước di trú thay cho kiểm tra dữ liệu.**

## 11. Chính sách `null`, copy và khả năng sửa của dữ liệu

Không thể coi “trả `List<User>`” là hợp đồng đầy đủ nếu chưa thống nhất các thuộc tính sau.

### `null`

Trong `MigrationBoundaryDemo`, `checkedUsers` từ chối `null` vì pattern `instanceof User` trả `false`. Nếu nghiệp vụ cho phép thiếu phần tử, hãy chọn một mô hình rõ ràng: giá trị mặc định, lọc bỏ có báo cáo, hoặc mô tả `Optional` ở lớp khác. `List.copyOf` cũng không chấp nhận phần tử `null`.

Với `SettingsGateway.read`, nếu key không tồn tại thì `LegacySettings.read` trả `null`; `Class.cast(null)` cho `null`. API production có thể cần phân biệt **key vắng mặt** với **giá trị đã tồn tại nhưng bằng null**.

### Alias và quyền sửa

Trả trực tiếp raw list từ legacy khiến mã typed có thể đang cầm một **alias** của collection mutable. Một legacy caller khác sửa danh sách có thể làm dữ liệu mới không còn đúng kiểu sau thời điểm bạn kiểm tra.

Tạo snapshot mới sau khi kiểm tra giúp loại bỏ việc chia sẻ **cấu trúc danh sách** trong trường hợp tuần tự của ví dụ. Nhưng nếu phần tử `User` có field mutable hoặc nguồn đang bị sửa đồng thời trong quá trình duyệt, cần cách quản lý quyền sở hữu, lock/snapshot hoặc dữ liệu bất biến sâu thích hợp. `List.copyOf` không phải giải pháp thay thế cơ chế đồng bộ.

### Thời điểm phát hiện lỗi

Một adapter có thể chọn:

- **Fail-fast**: ném exception tại phần tử sai đầu tiên, như ví dụ.
- **Collect-errors**: gom các lỗi validation kèm index, trả lại báo cáo để người dùng chỉnh.
- **Skip có chủ đích**: loại bỏ phần tử không hợp lệ nếu hợp đồng nghiệp vụ cho phép và có thống kê minh bạch.

Không lặng lẽ bỏ qua phần tử sai kiểu nếu người dùng tin rằng toàn bộ dữ liệu đã được xử lý đầy đủ.

## 12. Thiết kế test cho từng ranh giới

Bộ test có ý nghĩa của một migration boundary nên dựa vào **hợp đồng thực tế**, không chỉ vào chữ ký sau khi sửa. Với `checkedUsers` trong ví dụ, các trường hợp cần nghĩ đến:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Danh sách hợp lệ | Hai `User` | Hai phần tử đúng thứ tự |
| Danh sách rỗng | `List.of()` | Danh sách rỗng |
| Sai kiểu | `User`, sau đó `String` | Báo lỗi chỉ rõ index 1 |
| Giá trị `null` | Một phần tử `null` | Bị từ chối theo policy |
| Sửa nguồn sau khi chuyển | Thêm phần tử vào raw list | Snapshot cũ không thêm phần tử |
| Caller cố ghi vào kết quả | Gọi `add` trên list trả về | Bị từ chối nếu dùng `List.copyOf` |
| Nguồn bị sửa đồng thời | Thay đổi trong khi duyệt | Cần quy định/kiểm tra đồng bộ theo hợp đồng |
| Giá trị object bên trong mutable | Sửa field của phần tử | Cần xem xét có cần deep copy không |

Với `SettingsGateway`, kiểm thử đọc đúng token, token sai, key vắng mặt và giá trị `null`. Với API công khai đã tồn tại, thêm các bài kiểm tra build/callers hiện hữu để xác nhận source và binary compatibility nếu cần.

Một kiểm tra đặc biệt giá trị: **đặt dữ liệu sai kiểu vào nguồn raw trước**, rồi chứng minh phần typed không nhận dữ liệu đó theo hợp đồng. Nếu chỉ test đường thành công, bạn có thể bỏ sót lỗi thuộc chính mục tiêu chuyển đổi.

## 13. Các lỗi thường gặp khi di trú

**1. Thay `List` thành `List<Object>` cho tất cả trường hợp.**

Việc này làm mất cơ hội diễn đạt kiểu miền dữ liệu và có thể khiến `List<String>` không truyền được vào API do invariance. Hãy chọn theo mục đích: `List<?>` để đọc chưa rõ kiểu, `List<User>` sau validation, hoặc `List<Object>` khi muốn hỗn hợp kiểu thật.

**2. Cast `(List<User>) raw` ngay tại mọi caller.**

Mỗi cast làm tăng vùng cần tin tưởng, không kiểm tra các phần tử và khiến lỗi xuất hiện xa nguồn. Tập trung chuyển đổi tại một adapter đã kiểm chứng.

**3. Đổi return generic rồi mặc định dữ liệu đã được làm sạch.**

Chữ ký compile-time không tự chuyển string thành user, không từ chối phần tử sai lúc runtime và không cách ly danh sách mutable. Cần kiểm tra schema cùng chính sách quyền sở hữu dữ liệu.

**4. Thay tham số `Object` bằng `User` trên API public nhưng bỏ qua caller đã biên dịch.**

Descriptor có thể thay đổi, gây `NoSuchMethodError` hoặc lỗi liên kết khác khi chạy binary chưa được cập nhật. Cần xem xét adapter/phương thức song song và xác minh tương thích bằng build, `javap`, hoặc kiểm tra API.

**5. Tắt toàn bộ `unchecked` trong mã mới.**

Cảnh báo là tín hiệu chưa chứng minh được an toàn kiểu. Khoanh vùng ở nơi tiếp xúc legacy, ghi nhận nguyên nhân cụ thể, dần xóa khi nguồn đã typed.

**6. Kiểm tra `instanceof List<?>` rồi tưởng đã xác thực `List<User>`.**

Thao tác ấy chỉ xác minh kiểu container; để xác thực phần tử, duyệt và kiểm tra từng giá trị, hoặc dùng metadata/contract có căn cứ.

**7. Trộn việc di trú generics với đổi semantics của API.**

Nếu API cũ trả một collection live view còn API mới trả snapshot bất biến, đó là thay đổi hành vi cần diễn đạt rõ. Đôi khi thay đổi có chủ đích là cần thiết, nhưng phải cập nhật caller/test theo hợp đồng mới.

**8. Cố gắng generic hóa các miền dữ liệu không đồng nhất.**

Nếu một `List` chứa nhiều loại record có ý nghĩa nghiệp vụ, có thể cần một kiểu tổng quát rõ ràng (ví dụ sealed hierarchy), chuyển đổi thành các dạng domain riêng hoặc giữ `List<?>` tại điểm chưa đủ thông tin. Ép tất cả thành `List<User>` không giải quyết sự đa dạng dữ liệu.

## 14. Bài luyện tập: áp dụng di trú theo ranh giới

### Bài 1 — Tìm điểm nguy hiểm

Cho API cũ:

```java
static java.util.List load() {
    java.util.List data = new java.util.ArrayList();
    data.add("A");
    data.add(7);
    return data;
}
```

Đâu là rủi ro nếu caller mới viết `List<String> x = (List<String>) load();`?

**Gợi ý đáp án:** cast unchecked không kiểm tra từng phần tử, `Integer` sẽ gây lỗi khi đọc với kỳ vọng `String`. Di trú bằng adapter kiểm tra từng phần tử; fail-fast hoặc trả lỗi về caller.

### Bài 2 — Chọn chữ ký đích

Một API chỉ duyệt các phần tử của một `List` không biết kiểu; có nên chuyển sang `List<Object>`?

**Đáp án:** thường nên dùng `List<?>`. Nó nhận `List<String>`, `List<Integer>` và nhiều dạng khác mà không cho phép ghi tùy tiện.

### Bài 3 — Giới hạn của `Class<T>`

Adapter nhận `Class<T>` có thể kiểm tra `String.class`. Nó có xác minh được toàn bộ `List<String>` chỉ bằng `List.class` không?

**Đáp án:** không; `List.class` chỉ kiểm tra lớp/container. Kiểu tham số `String` bị xóa ở runtime descriptor; phải kiểm tra phần tử hoặc giữ thêm metadata/hợp đồng đáng tin.

### Bài 4 — Source, binary và dữ liệu

Thay `List findAll()` bằng `List<User> findAll()` có luôn an toàn không?

**Đáp án:** không có bảo đảm chung. Hai return type dùng cùng JVM descriptor `List` trong ví dụ, nhưng source callers, generic signature metadata, hợp đồng phần tử, quyền sửa collection và cách xử lý lỗi có thể khác. Cần kiểm tra API, hành vi và consumer cụ thể.

### Bài 5 — Lợi ích của snapshot

Vì sao ví dụ `checkedUsers` tạo `ArrayList<User>` và dùng `List.copyOf` thay vì trả raw list dưới một cast?

**Đáp án:** vừa kiểm tra từng phần tử vừa tạo danh sách mới, giúp caller typed không chia sẻ cấu trúc mutable với legacy list; kết quả cũng không thể sửa qua API list thông thường.

### Bài 6 — Thứ tự ưu tiên khi sửa hệ thống lớn

Một dự án có 20 caller dùng `Object` từ thư viện cũ; chỉ có 3 caller cần `User`. Có nên sửa ngay thư viện và 20 caller?

**Gợi ý:** xác định hợp đồng của 3 caller, tạo adapter chỉ phục vụ `User`, test dữ liệu sai, chuyển 3 caller trước. Sau khi quan sát các luồng khác, mới cân nhắc chỉnh nguồn và loại bỏ phần legacy phù hợp.

## Checklist áp dụng trên một ranh giới

Trước khi đánh dấu một đường di trú là hoàn chỉnh, hãy trả lời:

1. Có xác định **nguồn dữ liệu, quyền sở hữu, nơi sửa đổi** và loại dữ liệu thực không?
2. Có chọn đúng chữ ký API mới, tránh raw types trong lớp consumer không?
3. Dữ liệu từ legacy được **xác minh trước khi gắn cam kết generic typed** chưa?
4. Có chính sách rõ cho `null`, phần tử sai và báo lỗi không?
5. Collection trả về có cần snapshot/immutable hay được phép live view không?
6. Các cảnh báo `rawtypes`/`unchecked` còn nằm ở vùng nào, có được hiểu và giới hạn chưa?
7. Những thay đổi chữ ký public có được đánh giá về source, binary và behavioral compatibility không?
8. Các bài kiểm tra đúng/sai kiểu, dữ liệu rỗng, thay đổi sau khi trả về và caller cũ đã chạy chưa?

## Kết luận

**Di chuyển API cũ sang generics theo từng ranh giới** là cách biến sự không chắc chắn về kiểu thành một hợp đồng rõ ràng tại điểm dữ liệu đi vào phần mã mới. Raw `List` hoặc `Object` có thể được giữ tạm ở phía legacy; adapter đảm nhiệm kiểm tra, chuyển đổi, báo lỗi và bảo vệ quyền sở hữu dữ liệu; consumer mới dùng `List<User>` hoặc generic method có `Class<T>` mà không phải cast tùy tiện. Khi đã xác thực dữ liệu và caller ở một vùng, bạn có thể tiến đến vùng tiếp theo, đồng thời xem xét tương thích API bằng cả compiler, runtime và bytecode.
