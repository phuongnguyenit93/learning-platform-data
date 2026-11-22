# Mục đích và kiểu khóa của EnumMap

## 1. Khái niệm: ánh xạ từ một miền enum sang các giá trị

`EnumMap` là một triển khai `Map` chuyên dụng khi kiểu khóa là enum.

Ví dụ:

```java
// Khai báo minh họa.
enum Stage {
    CREATED,
    RUNNING,
    DONE,
    FAILED
}
```

Có thể ánh xạ mỗi giai đoạn sang một thông điệp:

```java
// Minh họa trong một phương thức; cần import java.util.EnumMap.
EnumMap<Stage, String> messages = new EnumMap<>(Stage.class);

messages.put(Stage.CREATED, "new");
messages.put(Stage.RUNNING, "working");
```

Ở đây:

- `Stage` là kiểu khóa.
- `String` là kiểu giá trị.
- Mỗi khóa đang có trong map ánh xạ tới một giá trị.
- Không có nhiều ánh xạ độc lập cho cùng một khóa; đặt lại khóa ấy sẽ thay giá trị cũ.

`EnumMap` phù hợp với các bảng cấu hình theo chế độ, thông điệp theo trạng thái, bộ xử lý theo loại sự kiện hoặc dữ liệu gắn với một tập khóa đã được mô hình hóa bằng enum.

Các quy tắc và API trong bài vẫn dùng trên Java hiện đại. Chương trình thực hành chạy trên Java 17 trở lên.

## 2. Vì sao chọn enum làm miền khóa?

So với việc dùng các chuỗi như `"RUNNING"`, một kiểu enum thể hiện một miền giá trị được đặt tên rõ trong mã nguồn.

```java
// Minh họa hợp lệ với messages như trên.
messages.put(Stage.RUNNING, "working");
```

Một chuỗi chỉ trông giống tên hằng không tự trở thành khóa enum:

```java
// Minh họa lỗi; không biên dịch.
messages.put("RUNNING", "working");
```

Lợi ích không chỉ là tránh một số lỗi gõ sai. Hợp đồng kiểu cho biết ngay bảng dữ liệu đang được phân chia theo khái niệm nào.

Nếu khóa là các mã do người dùng tự nhập hoặc các giá trị được bổ sung động mà chưa thuộc enum, trước hết phải xác định mô hình miền phù hợp. Không nên tạo một enum chỉ để ép một tập khóa động vào `EnumMap`.

Một `HashMap<Stage, V>` cũng có thể chứa khóa enum. `EnumMap` khai thác thông tin miền enum để có biểu diễn chuyên biệt và thứ tự duyệt được bảo đảm theo khai báo hằng.

## 3. Ràng buộc kiểu khóa: K extends Enum<K>

Dạng khai báo kiểu của lớp là:

```text
EnumMap<K extends Enum<K>, V>
```

Điều cần hiểu:

- `K` phải là kiểu enum thích hợp, chẳng hạn `Stage`.
- Tất cả khóa của một `EnumMap` thuộc cùng kiểu enum đã được xác định khi tạo map.
- `V` không bị yêu cầu là enum; nó là kiểu giá trị tham chiếu phù hợp với bài toán.

Ví dụ các kiểu hợp lệ:

```java
// Khai báo minh họa; cần import EnumMap và List.
EnumMap<Stage, String> messages;
EnumMap<Stage, Integer> retries;
EnumMap<Stage, List<String>> notes;
```

Không thể chọn `String` hay `Integer` làm `K` chỉ vì muốn tận dụng biểu diễn của `EnumMap`. Chúng không phải kiểu enum.

Hai enum khác nhau vẫn là hai kiểu khác nhau, dù cùng có hằng tên `RUNNING`:

```java
// Khai báo minh họa độc lập.
enum Stage {
    CREATED, RUNNING, DONE, FAILED
}

enum OtherStage {
    RUNNING
}
```

`OtherStage.RUNNING` không dùng thay cho `Stage.RUNNING` ở `put` của `EnumMap<Stage, String>`.

Một `EnumMap` cũng không phải “map chứa khóa thuộc bất kỳ enum nào”. Nếu có nhiều miền enum độc lập, cần giữ chúng trong các cấu trúc hoặc mô hình có hợp đồng rõ, thay vì bỏ kiểm tra kiểu.

## 4. Vì sao constructor cần Stage.class?

Cách tạo thường dùng:

```java
// Minh họa trong một phương thức.
EnumMap<Stage, String> messages = new EnumMap<>(Stage.class);
```

`Stage.class` cung cấp đối tượng `Class` xác định miền khóa ở runtime. Thư viện cần thông tin ấy ngay cả khi map chưa có khóa nào.

Sau khi tạo:

```java
// Minh họa.
int size = messages.size();  // 0.
```

Biết enum có bốn hằng không có nghĩa map tự tạo bốn ánh xạ. Nó chỉ biết những khóa nào được phép; các ánh xạ thực tế vẫn do chương trình thêm.

`EnumMap` không có constructor rỗng dạng `new EnumMap<>()` không kèm thông tin nguồn hoặc kiểu khóa.

### Sao chép từ một EnumMap

```java
// Minh họa trong một phương thức.
EnumMap<Stage, String> original = new EnumMap<>(Stage.class);
EnumMap<Stage, String> copy = new EnumMap<>(original);
```

Ngay cả khi `original` rỗng, nó vẫn giữ miền khóa nên bản sao xác định được kiểu enum.

### Sao chép từ một Map thông thường

Có constructor nhận `Map`:

```java
// Minh họa với source là Map<Stage, String> có phần tử.
EnumMap<Stage, String> copy = new EnumMap<>(source);
```

Nếu nguồn là một map rỗng không phải `EnumMap`, constructor không có khóa hoặc metadata `EnumMap` để xác định kiểu enum; nó ném `IllegalArgumentException`.

Kiểu generic ghi ở mã nguồn không tự trở thành đối số `Stage.class`. Khi đã biết cần một map rỗng của `Stage`, truyền `Stage.class` trực tiếp là cách rõ ràng.

## 5. Giá trị không bị giới hạn thành enum

Khóa là enum không có nghĩa giá trị cũng phải là một hằng enum.

Ví dụ:

```java
// Minh họa trong một phương thức.
EnumMap<Stage, Integer> retryLimits = new EnumMap<>(Stage.class);
retryLimits.put(Stage.CREATED, 0);
retryLimits.put(Stage.RUNNING, 3);
```

Giá trị nguyên thủy ở lời gọi được boxing theo hợp đồng `Integer` phù hợp. Không viết `EnumMap<Stage, int>`, vì đối số kiểu generic phải là kiểu tham chiếu.

Hai khóa khác nhau có thể ánh xạ tới cùng một giá trị. Yêu cầu không trùng áp dụng cho khóa, không yêu cầu mọi giá trị phải khác nhau.

Giá trị cũng có thể là một đối tượng cấu hình, danh sách hoặc thao tác được mô hình hóa bằng một interface. Việc chọn kiểu `V` cần thể hiện đúng nội dung bảng ánh xạ.

Một kiểu giá trị chung quá rộng như `Object` có thể làm người đọc phải ép kiểu ở nơi sử dụng. Không dùng nó chỉ để gom những dữ liệu không có cùng hợp đồng vào một map.

## 6. Null ở khóa và null ở giá trị có hợp đồng khác nhau

`EnumMap` không cho thêm khóa `null`:

```java
// Minh họa lỗi runtime.
messages.put(null, "unknown");
```

Thao tác này ném `NullPointerException`. `null` không phải một hằng thuộc miền enum.

Ngược lại, `EnumMap` cho phép giá trị `null`:

```java
// Minh họa trong một phương thức.
messages.put(Stage.FAILED, null);
```

Điều đó tạo một ánh xạ cho khóa `FAILED`, với giá trị hiện tại là `null`.

Hai trường hợp dưới đây khác nhau:

| Trạng thái | get(key) | containsKey(key) |
| --- | --- | --- |
| Chưa có ánh xạ cho khóa | `null` | `false` |
| Có ánh xạ tới giá trị `null` | `null` | `true` |

Nếu ứng dụng cần phân biệt chúng, không chỉ kiểm tra kết quả `get`.

Thao tác kiểm tra sự có mặt của khóa `null` hoặc loại bỏ khóa ấy được xử lý như không có khóa tương ứng; điều đó không cho phép thêm khóa `null`.

Với các giá trị lớp bao như `Integer`, đọc một giá trị `null` rồi gán trực tiếp cho `int` vẫn có thể gây lỗi unboxing. `EnumMap` không tự thay dữ liệu thiếu bằng `0`.

## 7. Miền khóa hữu hạn không đồng nghĩa bảng đã đầy đủ

Một map mới biết kiểu khóa nhưng có thể bỏ trống bất kỳ hằng nào.

Nếu nghiệp vụ yêu cầu mỗi `Stage` đều có một cấu hình, đó là điều kiện bổ sung cần kiểm tra. Có thể xét từng hằng từ `Stage.values()` hoặc tạo tập các khóa còn thiếu:

```java
// Minh họa; cần import java.util.EnumSet.
EnumSet<Stage> missing = EnumSet.allOf(Stage.class);
missing.removeAll(messages.keySet());
```

`missing` cho biết hằng nào chưa có ánh xạ. Nó không phát hiện ánh xạ có giá trị `null`, vì khóa của ánh xạ ấy vẫn hiện diện.

Nếu cần “đầy đủ và khác null”, phải kiểm tra cả hai yêu cầu. Khi thêm hằng enum mới, điều kiện đầy đủ cũng cần được xem xét lại; map không tự sinh giá trị cấu hình cho hằng mới.

Đây là ví dụ cho sự phân biệt giữa hợp đồng kiểu và tính đầy đủ dữ liệu: kiểu khóa có thể đúng hoàn toàn nhưng bảng vẫn thiếu những ánh xạ cần thiết.

## 8. Thứ tự duyệt và biểu diễn chuyên biệt

`EnumMap` duy trì thứ tự tự nhiên của các khóa enum, tức thứ tự khai báo hằng:

```java
// Minh họa trong một phương thức.
EnumMap<Stage, String> messages = new EnumMap<>(Stage.class);
messages.put(Stage.DONE, "done");
messages.put(Stage.CREATED, "new");
messages.put(Stage.RUNNING, "working");

System.out.println(messages);
```

Kết quả:

```text
{CREATED=new, RUNNING=working, DONE=done}
```

Thứ tự không theo lần chèn hoặc thứ tự chữ cái. Các cách nhìn `keySet()`, `entrySet()` và `values()` phản ánh thứ tự khóa tương ứng.

Thư viện dùng biểu diễn mảng chuyên biệt cho miền enum; ứng dụng không cần tự biến khóa thành số chỉ mục để tra cứu. Lợi thế này gắn với việc miền khóa cố định theo một kiểu enum.

Không dùng vị trí nội bộ hoặc `ordinal()` làm định dạng lưu trữ ổn định cho dữ liệu bên ngoài chỉ vì cấu trúc tận dụng thứ tự enum. Biểu diễn trong collection và hợp đồng trao đổi dữ liệu là hai trách nhiệm khác nhau.

Không đưa ra một số byte hoặc hệ số hiệu năng cố định cho mọi môi trường; đặc điểm quan trọng ở đây là cấu trúc chuyên dụng cho khóa enum và các bảo đảm API.

## 9. Thay giá trị, sao chép và cách nhìn Map

Đặt lại cùng khóa thay thế giá trị cũ:

```java
// Minh họa trong một phương thức có messages.
String previous = messages.put(Stage.RUNNING, "running");
```

`previous` nhận giá trị trước đó nếu có. Số ánh xạ không tăng chỉ vì giá trị của khóa `RUNNING` được thay.

Bản sao map có cấu trúc ánh xạ riêng. Xóa khóa khỏi bản sao không tự xóa khóa ở map gốc. Tuy nhiên, các giá trị tham chiếu được sao chép như tham chiếu; nếu `V` là một đối tượng thay đổi được, hai map có thể cùng trỏ tới đối tượng giá trị ấy. Sao chép map không phải sao chép sâu mọi dữ liệu bên trong.

Có thể dùng kiểu giao diện tại ranh giới API:

```java
// Minh họa.
Map<Stage, String> messages = new EnumMap<>(Stage.class);
```

Đối tượng runtime vẫn là `EnumMap`; kiểu biến `Map` không làm nó đổi sang biểu diễn khác.

`EnumMap` không tự đồng bộ cho nhiều luồng. Iterator có tính nhất quán yếu, không ném `ConcurrentModificationException`, nhưng điều đó không thay thế thiết kế phối hợp khi có truy cập đồng thời và sửa dữ liệu. Chương trình trong bài sử dụng map tuần tự.

## 10. Chương trình đầy đủ

Lưu vào `EnumMapKeyDemo.java`:

```java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;

public class EnumMapKeyDemo {
    enum Stage {
        CREATED,
        RUNNING,
        DONE,
        FAILED
    }

    public static void main(String[] args) {
        EnumMap<Stage, String> messages = new EnumMap<>(Stage.class);
        System.out.println("initialSize=" + messages.size());

        messages.put(Stage.DONE, "done");
        messages.put(Stage.CREATED, "new");
        messages.put(Stage.RUNNING, "working");
        System.out.println(messages);

        String previous = messages.put(Stage.RUNNING, "running");
        System.out.println("previous=" + previous);
        System.out.println("size=" + messages.size());

        System.out.println("missing=" + messages.get(Stage.FAILED));
        System.out.println("hasFailed=" + messages.containsKey(Stage.FAILED));

        messages.put(Stage.FAILED, null);
        System.out.println("hasFailedAfterPut="
                + messages.containsKey(Stage.FAILED));
        System.out.println("failedValue=" + messages.get(Stage.FAILED));

        try {
            messages.put(null, "unknown");
        } catch (NullPointerException ex) {
            System.out.println("null key rejected");
        }

        EnumMap<Stage, String> copy = new EnumMap<>(messages);
        copy.remove(Stage.CREATED);
        System.out.println("originalHasCreated="
                + messages.containsKey(Stage.CREATED));
        System.out.println("copyHasCreated="
                + copy.containsKey(Stage.CREATED));

        EnumMap<Stage, String> empty = new EnumMap<>(Stage.class);
        EnumMap<Stage, String> emptyCopy = new EnumMap<>(empty);
        System.out.println("emptyCopySize=" + emptyCopy.size());

        Map<Stage, String> genericEmpty = new HashMap<>();
        try {
            new EnumMap<>(genericEmpty);
        } catch (IllegalArgumentException ex) {
            System.out.println("empty map needs key type");
        }

        EnumSet<Stage> missingKeys = EnumSet.allOf(Stage.class);
        missingKeys.removeAll(messages.keySet());
        System.out.println("unmapped=" + missingKeys);

        for (Map.Entry<Stage, String> entry : messages.entrySet()) {
            System.out.println(entry.getKey() + "=" + entry.getValue());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapKeyDemo.java
java EnumMapKeyDemo
```

Stdout chính xác:

```text
initialSize=0
{CREATED=new, RUNNING=working, DONE=done}
previous=working
size=3
missing=null
hasFailed=false
hasFailedAfterPut=true
failedValue=null
null key rejected
originalHasCreated=true
copyHasCreated=false
emptyCopySize=0
empty map needs key type
unmapped=[]
CREATED=new
RUNNING=running
DONE=done
FAILED=null
```

Các điểm cần đối chiếu:

1. Constructor biết miền enum nhưng không tự tạo ánh xạ.
2. Chèn theo thứ tự khác vẫn duyệt theo thứ tự khai báo khóa.
3. Đặt lại `RUNNING` thay giá trị, không tăng số ánh xạ.
4. “Không có khóa” và “có khóa tới null” khác nhau ở `containsKey`.
5. Khóa `null` bị từ chối dù giá trị `null` được phép.
6. Sao chép cấu trúc map cho phép xóa ánh xạ ở bản sao mà không xóa ở bản gốc.
7. `EnumMap` rỗng giữ metadata khóa, còn `HashMap` rỗng không cung cấp đủ thông tin cho constructor sao chép.
8. `unmapped=[]` chỉ chứng minh đủ khóa, không chứng minh mọi giá trị khác `null`.

Các ngoại lệ được bắt để minh họa các hợp đồng độc lập trong một lần chạy. Mã ứng dụng nên tạo cấu trúc đúng kiểu và xử lý dữ liệu thiếu theo yêu cầu thay vì dùng ngoại lệ làm luồng xử lý thông thường.

## 11. Cách chọn cấu trúc và tự luyện

| Yêu cầu dữ liệu | Cấu trúc thường phù hợp |
| --- | --- |
| Chỉ cần biết hằng enum có thuộc một nhóm không | `EnumSet<E>` |
| Mỗi khóa thuộc một enum ánh xạ sang một giá trị | `EnumMap<E, V>` |
| Khóa là dữ liệu tham chiếu tổng quát, không có miền enum phù hợp | Một `Map` tổng quát theo hợp đồng cần thiết |

Những lỗi cần tránh:

- Tưởng mọi hằng enum tự có một ánh xạ sau constructor.
- Trộn hằng từ enum khác chỉ vì cùng tên.
- Nhầm không cho khóa `null` với không cho giá trị `null`.
- Dùng `get(key) == null` để kết luận chắc chắn khóa chưa có.
- Sao chép một map rỗng thông thường mà không cung cấp kiểu khóa.
- Tưởng bản sao map là bản sao sâu của các giá trị.
- Tưởng thứ tự chèn quyết định thứ tự duyệt.

Bài tập:

1. Tạo `EnumMap<Stage, Integer>` lưu giới hạn thử lại; xác định rõ chính sách cho khóa chưa có và giá trị `null`.
2. Chèn các khóa theo thứ tự ngược khai báo rồi in `keySet`, `values` và `entrySet`.
3. Thử đưa một hằng của enum khác vào `put` và giải thích lỗi kiểu.
4. Kiểm tra điều kiện “mọi Stage có ánh xạ khác null” mà không chỉ dựa vào `size()`.
5. Vì sao constructor từ một `EnumMap` rỗng hoạt động, còn từ một `HashMap` rỗng có thể thất bại?
6. Nếu giá trị là `List<String>`, việc sao chép map có tự sao chép từng danh sách không?
7. Phân biệt yêu cầu “nhóm Stage đang bật” với “mỗi Stage có một thông điệp” để chọn giữa `EnumSet` và `EnumMap`.

## Tài liệu đối chiếu

- [Java API — EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html): kiểu khóa, constructor, thứ tự, null và sao chép.
- [Java API — Map.containsKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#containsKey(java.lang.Object)): kiểm tra sự có mặt của ánh xạ.
- [Java API — Enum](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html): kiểu enum và các collection chuyên dụng liên quan.
