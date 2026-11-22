# Chính sách một khóa null và nhiều giá trị null

## 1. Hai vị trí null có hai vai trò khác nhau

Một `HashMap<K, V>` lưu các ánh xạ từ khóa đến giá trị. Nó cho phép:

- Tối đa một ánh xạ có khóa là `null` trong cùng một map.
- Nhiều ánh xạ khác nhau cùng có giá trị là `null`.
- Một ánh xạ đồng thời có khóa `null` và giá trị `null`.

Cần đọc “nhiều giá trị null” là **nhiều ánh xạ có phần giá trị null**, không phải một khóa tự chứa nhiều giá trị hiện tại. Mỗi khóa vẫn chỉ xác định nhiều nhất một giá trị.

Ví dụ, một map có thể biểu diễn:

```text
null     → "nội dung mặc định"
"draft"  → null
"review" → null
```

Khóa nằm bên trái để nhận diện ánh xạ. Giá trị bên phải là dữ liệu được gắn với khóa đó. Việc giá trị được phép lặp không làm khóa được phép trùng.

### Vì sao cần hiểu chính sách này?

Nếu ứng dụng cho phép dữ liệu chưa biết, `null` có thể xuất hiện trong lúc lưu và đọc. Khi đó `get` trả `null` chưa đủ để kết luận không có khóa; việc ghi `null` cũng không đồng nghĩa xóa ánh xạ.

Ngược lại, nếu nghiệp vụ cấm `null`, việc `HashMap` chấp nhận nó không có nghĩa mọi đầu vào null đều hợp lệ. Khả năng của thư viện và quy tắc dữ liệu của ứng dụng là hai tầng cần tách.

Bài đi từ cấu trúc khóa–giá trị đến cách đọc, cập nhật, duyệt và chuyển dữ liệu. Các ví dụ đều dùng `HashMap` thật, không dựa vào thứ tự duyệt mà lớp này không bảo đảm.

## 2. Vì sao chỉ có một khóa null?

Map không lưu hai ánh xạ riêng cho cùng một khóa logic. Gọi `put(null, value)` lần đầu có thể tạo ánh xạ; gọi lại với khóa `null` thay giá trị của ánh xạ đó.

```text
put(null, "first")
    → null → "first"

put(null, "second")
    → null → "second"
    → không tạo thêm một khóa null thứ hai
```

Quy tắc này áp dụng trong từng map, không phải một giới hạn “toàn chương trình chỉ được có một null”. Hai đối tượng `HashMap` khác nhau có thể mỗi đối tượng chứa ánh xạ khóa null của riêng nó.

`null` là một tham chiếu không trỏ tới đối tượng; không có một lớp riêng của null để tạo các khóa null theo từng loại. Nếu nhiều biến đều có giá trị null và được dùng làm khóa trong cùng một map chấp nhận chúng, chúng không trở thành những định danh khác nhau chỉ vì tên biến khác nhau.

### Không dùng null làm mã tạm cho nhiều bản ghi khác nhau

Nếu ba bản ghi chưa có mã đều được ghi bằng khóa `null`, các lần ghi sau sẽ thay ánh xạ trước. Bạn không có ba bản ghi độc lập chỉ vì ba đối tượng giá trị khác nhau.

Nếu nghiệp vụ phải giữ nhiều bản ghi chưa xác định mã, cần một cách nhận diện thích hợp, chẳng hạn mã tạm duy nhất, kiểu khóa riêng hoặc cấu trúc danh sách nếu bản chất dữ liệu là một chuỗi bản ghi. Không mong một map bỏ qua tính duy nhất của khóa chỉ cho trường hợp null.

### null khác chuỗi "null"

Đoạn sau là minh họa đặt trong một phương thức, với một map rỗng:

```java
Map<String, String> map = new HashMap<>();
map.put(null, "default");
map.put("null", "literal");

// map.size() là 2.
// map.get(null) là "default".
// map.get("null") là "literal".
```

`"null"` là một đối tượng chuỗi có bốn ký tự, còn `null` là tham chiếu không có đối tượng. Tự chuyển null thành chuỗi `"null"` có thể làm mất khác biệt này nếu dữ liệu thật cũng được phép dùng chuỗi ấy làm khóa.

### HashMap nhận null không có nghĩa có thể gọi phương thức trên null

`map.get(null)`, `map.put(null, value)` và `map.containsKey(null)` được `HashMap` hỗ trợ. Hiện thực xử lý trường hợp khóa null theo hợp đồng của nó; ứng dụng không cần và không thể gọi `null.hashCode()` hay `null.equals(...)`.

Một `NullPointerException` do mã của ứng dụng gọi phương thức trên khóa null không phải bằng chứng rằng `HashMap` không chấp nhận khóa đó.

## 3. Vì sao nhiều giá trị null vẫn hợp lệ?

Giá trị của map không bắt buộc duy nhất. Cũng như hai khóa có thể cùng mang số `3`, hai hoặc nhiều khóa có thể cùng mang giá trị `null`.

```text
"draft"  → null
"review" → null
"final"  → null
```

Map trên có ba ánh xạ. Kích thước là `3`, dù không có giá trị nào khác null.

Nếu thêm ánh xạ `null → null`, kích thước có thể thành `4`: khóa null là một khóa khác với ba chuỗi đang có. Ghi lại `put("draft", null)` sau đó không làm kích thước tăng nữa, vì khóa `"draft"` đã tồn tại.

| Câu hỏi | Phương thức phù hợp |
|---|---|
| Có ánh xạ cho khóa null không? | `containsKey(null)` |
| Giá trị của khóa null hiện là gì? | `get(null)` |
| Có ít nhất một ánh xạ mang giá trị null không? | `containsValue(null)` |
| Có bao nhiêu ánh xạ? | `size()` |
| Có bao nhiêu ánh xạ mang giá trị null? | Duyệt giá trị hoặc entry và đếm theo điều kiện |

`containsValue(null)` chỉ trả `boolean`: nó không cho biết có bao nhiêu null, không chỉ ra khóa nào, và không chứng minh khóa null có tồn tại.

Các mối quan hệ độc lập có thể là:

- Không có khóa null nhưng vẫn có nhiều giá trị null.
- Có khóa null nhưng không có giá trị null nào.
- Có cả khóa null và giá trị null.
- Không có cả hai.

## 4. Chương trình đầy đủ: một khóa null, nhiều giá trị null

```java
import java.util.HashMap;
import java.util.Map;

public class HashMapNullPolicyDemo {
    public static void main(String[] args) {
        Map<String, String> messages = new HashMap<>();

        System.out.println("firstNullKeyOld="
                + messages.put(null, "default"));
        System.out.println("secondNullKeyOld="
                + messages.put(null, "fallback"));
        System.out.println("sizeAfterNullKeyWrites=" + messages.size());
        System.out.println("nullKeyValue=" + messages.get(null));

        messages.put("draft", null);
        messages.put("review", null);
        System.out.println("sizeAfterNamedNullValues=" + messages.size());
        System.out.println("hasNullValue=" + messages.containsValue(null));

        System.out.println("oldBeforeNullNull="
                + messages.put(null, null));
        System.out.println("hasNullKey=" + messages.containsKey(null));
        System.out.println("nullKeyNow=" + messages.get(null));
        System.out.println("finalSize=" + messages.size());

        int nullKeyCount = 0;
        int nullValueCount = 0;
        for (Map.Entry<String, String> entry : messages.entrySet()) {
            if (entry.getKey() == null) {
                nullKeyCount++;
            }
            if (entry.getValue() == null) {
                nullValueCount++;
            }
        }
        System.out.println("nullKeyCount=" + nullKeyCount);
        System.out.println("nullValueCount=" + nullValueCount);
    }
}
```

Lưu thành `HashMapNullPolicyDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPolicyDemo.java
java HashMapNullPolicyDemo
```

Đầu ra chính xác:

```text
firstNullKeyOld=null
secondNullKeyOld=default
sizeAfterNullKeyWrites=1
nullKeyValue=fallback
sizeAfterNamedNullValues=3
hasNullValue=true
oldBeforeNullNull=fallback
hasNullKey=true
nullKeyNow=null
finalSize=3
nullKeyCount=1
nullValueCount=3
```

### Giải thích các mốc

Hai lần ghi khóa null tạo một ánh xạ duy nhất:

- Lần đầu trả `null` vì chưa có giá trị cũ.
- Lần thứ hai trả `"default"`, rồi giá trị hiện tại thành `"fallback"`.
- Kích thước sau hai lần ghi vẫn là `1`.

Hai khóa chuỗi `"draft"` và `"review"` được thêm với giá trị null, đưa kích thước lên `3`.

Cuối cùng `put(null, null)` thay giá trị của khóa null từ `"fallback"` thành null. Kích thước vẫn `3`; lúc này cả ba ánh xạ đều mang giá trị null.

Hai bộ đếm cuối có ý nghĩa khác nhau:

```text
nullKeyCount=1
nullValueCount=3
```

Không cần dựa vào việc khóa null được in ở đâu trong thứ tự duyệt. Chương trình chỉ đếm hoặc đọc theo khóa cụ thể, nên đầu ra không phụ thuộc một thứ tự tình cờ của `HashMap`.

## 5. Ba trạng thái khi đọc một khóa

Với một khóa `k`, cần phân biệt:

| Trạng thái | `get(k)` | `containsKey(k)` |
|---|---|---|
| Không có ánh xạ của `k` | `null` | `false` |
| Có ánh xạ `k → null` | `null` | `true` |
| Có ánh xạ `k → "ready"` | `"ready"` | `true` |

Bảng áp dụng cả khi `k` là khóa null trong một `HashMap`. Khóa null không làm biến mất sự khác nhau giữa “chưa có ánh xạ” và “đã có ánh xạ với giá trị null”.

Nếu nghiệp vụ phân biệt “chưa ghi nhận” với “đã ghi nhận nhưng chưa có giá trị”, hãy giữ sự khác nhau đó khi đọc. Chỉ kiểm tra `get(k) != null` sẽ gộp hai trạng thái đầu.

### getOrDefault không thay tất cả null bằng giá trị dự phòng

`getOrDefault(k, fallback)` chọn `fallback` khi **không có ánh xạ** của khóa. Nếu khóa có ánh xạ với giá trị null, kết quả vẫn là null.

Vì vậy tên “default” không đồng nghĩa “mọi kết quả null sẽ được đổi thành một giá trị khác”. Phải chọn đúng quy tắc:

- Dự phòng khi không có khóa.
- Dự phòng khi giá trị null, bất kể có khóa hay chưa.
- Giữ hai tình huống riêng để xử lý khác nhau.

Hai quy tắc đầu khác nhau về ý nghĩa, dù trong một ứng dụng cấm giá trị null chúng có thể cho cùng kết quả ở các dữ liệu hợp lệ.

Đọc bằng `get` hay `getOrDefault` cũng không tự chèn một khóa mới. Một giá trị dự phòng được trả ra chưa có nghĩa nó đã được lưu vào map.

### Optional không tự bảo toàn thông tin sự tồn tại

Nếu bọc `Optional.ofNullable(map.get(k))`, cả không có ánh xạ lẫn có ánh xạ giá trị null đều tạo `Optional.empty()`. Cách bọc có thể phù hợp nếu ứng dụng chủ động gộp hai trạng thái, nhưng không giúp giữ lại sự khác nhau đã bị bỏ qua.

Khi cần mô tả nhiều trạng thái nghiệp vụ, có thể dùng một kiểu kết quả thể hiện rõ trạng thái hoặc kết hợp thông tin sự tồn tại theo một cơ chế truy cập được kiểm soát.

## 6. Ghi null khác xóa ánh xạ

Với một `HashMap` sửa được:

| Thao tác thành công | Trạng thái sau thao tác |
|---|---|
| `put(k, null)` | Khóa `k` có ánh xạ; giá trị là null |
| `remove(k)` | Khóa `k` không còn ánh xạ |
| `remove(k, null)` | Chỉ xóa nếu đang có ánh xạ của `k` với giá trị null |

`put(k, null)` không phải bí danh của `remove(k)`. Nếu dữ liệu dùng null để biểu diễn trạng thái “đã có bản ghi, chưa có giá trị”, xóa ánh xạ sẽ làm mất chính thông tin “đã có bản ghi”.

`put` và `remove` một tham số trả giá trị cũ. Kết quả null ở đây vẫn có hai khả năng: trước đó không có ánh xạ, hoặc có ánh xạ giá trị null.

Nếu cần biết trước đó có khóa không, trong tình huống một luồng sở hữu dữ liệu có thể ghi nhận `containsKey(k)` trước thao tác. Kiểm tra sau `remove` không khôi phục được sự khác nhau, vì cả “vốn không có” và “vừa bị xóa” đều có thể không có khóa sau đó.

Cặp lời gọi riêng không tự là thao tác nguyên tử. `HashMap` không cung cấp cơ chế đồng bộ cho nhiều luồng cùng thay đổi dữ liệu; không suy khả năng phân biệt trạng thái an toàn đồng thời chỉ từ hai dòng `containsKey` rồi `remove`.

### Xóa qua values chỉ xóa một hay tất cả?

`map.values().remove(null)` xóa một lần xuất hiện giá trị null nếu có, tức bỏ một ánh xạ tương ứng trong map. Nó không tự xóa hết các ánh xạ đang có giá trị null.

Nếu cần xóa tất cả, có thể dùng `removeIf(Objects::isNull)` trên view giá trị của map sửa được. Phải quyết định rõ điều này có đúng nghiệp vụ hay không: lọc hết null là bỏ các ánh xạ, không chỉ dọn một cách biểu diễn.

## 7. Chương trình đầy đủ: tồn tại, giá trị dự phòng và xóa

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashMapNullPresenceDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();
        states.put("draft", null);

        System.out.println("draftGet=" + states.get("draft"));
        System.out.println("missingGet=" + states.get("missing"));
        System.out.println("hasDraft=" + states.containsKey("draft"));
        System.out.println("hasMissing=" + states.containsKey("missing"));
        System.out.println("draftOrDefault="
                + states.getOrDefault("draft", "fallback"));
        System.out.println("missingOrDefault="
                + states.getOrDefault("missing", "fallback"));
        System.out.println("sizeAfterReads=" + states.size());

        boolean existed = states.containsKey("draft");
        String removedOld = states.remove("draft");
        System.out.println("existedBeforeRemove=" + existed);
        System.out.println("removedOld=" + removedOld);
        System.out.println("hasDraftAfterRemove="
                + states.containsKey("draft"));

        states.put("draft", null);
        System.out.println("conditionalNullRemove="
                + states.remove("draft", null));
        System.out.println("sizeAfterConditionalRemove=" + states.size());

        states.put("a", null);
        states.put("b", null);
        states.put("c", null);
        System.out.println("oneNullRemoved=" + states.values().remove(null));
        System.out.println("sizeAfterOneNullRemove=" + states.size());
        System.out.println("stillHasNullValue=" + states.containsValue(null));
        System.out.println("allNullsRemoved="
                + states.values().removeIf(Objects::isNull));
        System.out.println("finalSize=" + states.size());
    }
}
```

Lưu thành `HashMapNullPresenceDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPresenceDemo.java
java HashMapNullPresenceDemo
```

Đầu ra chính xác:

```text
draftGet=null
missingGet=null
hasDraft=true
hasMissing=false
draftOrDefault=null
missingOrDefault=fallback
sizeAfterReads=1
existedBeforeRemove=true
removedOld=null
hasDraftAfterRemove=false
conditionalNullRemove=true
sizeAfterConditionalRemove=0
oneNullRemoved=true
sizeAfterOneNullRemove=2
stillHasNullValue=true
allNullsRemoved=true
finalSize=0
```

### Đọc đúng các kết quả giống nhau

`draftGet` và `missingGet` đều null, nhưng `hasDraft=true`, `hasMissing=false`. Hai phép đọc không làm kích thước tăng.

`draftOrDefault=null`, còn `missingOrDefault=fallback`, đúng theo quy tắc dự phòng chỉ khi không có ánh xạ.

Lần xóa `"draft"` trả `removedOld=null` nhưng thực sự có tác dụng vì `existedBeforeRemove=true` và sau đó khóa không còn. Overload `remove("draft", null)` lại trả một cờ `boolean`: `true` nói việc xóa theo điều kiện đã thực hiện được, không phải một giá trị cũ kiểu chuỗi.

Sau khi thêm `"a"`, `"b"`, `"c"` đều có giá trị null, xóa một lần qua `values().remove(null)` để lại kích thước `2` và vẫn còn null. Chương trình cố ý không khẳng định khóa nào trong ba khóa bị chọn. Lần `removeIf` sau đó mới lọc hết những ánh xạ còn lại.

## 8. Các phương thức cập nhật không diễn giải null giống nhau

Việc `HashMap` cho lưu giá trị null không có nghĩa mọi phương thức coi null là một giá trị bình thường trong mọi vị trí.

Bảng dưới giả sử map sửa được, hàm truyền vào hợp lệ, không tự sửa map trong lúc tính và không có truy cập đồng thời gây thay đổi:

| Phương thức | Nếu đang có ánh xạ với giá trị null |
|---|---|
| `get(k)` | Trả null |
| `getOrDefault(k, fallback)` | Vẫn trả null vì khóa có ánh xạ |
| `putIfAbsent(k, v)` | Có thể ghi `v`; coi giá trị null là chưa có giá trị để giữ |
| `computeIfAbsent(k, fn)` | Gọi hàm để thử tính giá trị khác null |
| `computeIfPresent(k, fn)` | Không gọi hàm, vì cần giá trị hiện tại khác null |
| `compute(k, fn)` | Gọi hàm với giá trị cũ null; kết quả null có ý nghĩa xóa ánh xạ |
| `merge(k, incoming, fn)` | Dùng `incoming` khác null mà không cần ghép với giá trị cũ null |

### 8.1. putIfAbsent không đồng nghĩa containsKey là false

Tên phương thức dễ khiến người đọc nghĩ nó chỉ ghi khi không có khóa. Hợp đồng còn gồm trường hợp khóa đang ánh xạ tới null.

Nếu ứng dụng muốn giữ null như một trạng thái đã ghi nhận có ý nghĩa, không nên dùng `putIfAbsent` rồi mong nó luôn bảo vệ trạng thái đó khỏi bị thay. Cần chọn quy tắc dựa trên yêu cầu thật về sự tồn tại của ánh xạ.

### 8.2. computeIfAbsent trả null không tạo một giá trị null mới

Nếu hàm trả một giá trị khác null, phương thức có thể ghi giá trị đó khi trước đó thiếu giá trị hoặc đang có null.

Nếu hàm trả null:

- Khóa vốn chưa có vẫn không được tạo ánh xạ mới.
- Khóa vốn đã có ánh xạ giá trị null vẫn giữ ánh xạ null đó.

Điều này khác với việc hiểu “trả null thì xóa hết dấu vết của khóa”. Chương trình tiếp theo kiểm chứng riêng hai trường hợp.

Một hệ quả khi dùng làm bộ nhớ đệm: nếu hàm tải trả null cho kết quả không tìm thấy, `computeIfAbsent` không tự lưu một kết quả khác null để đánh dấu đã kiểm tra. Lời gọi sau vẫn có thể phải gọi hàm tải lại. Nếu cần ghi nhớ “đã kiểm tra nhưng không có kết quả”, nên dùng một cách biểu diễn trạng thái rõ ràng theo thiết kế của ứng dụng.

### 8.3. computeIfPresent cần giá trị khác null

Một khóa vẫn có thể `containsKey(k) == true` nhưng `computeIfPresent` không chạy hàm vì giá trị hiện tại là null.

Vì vậy chữ “Present” trong tên phương thức không thể được đọc tách khỏi điều kiện cụ thể của hợp đồng. Nó không chỉ là kiểm tra sự tồn tại của khóa.

Nếu hàm thực sự được gọi cho giá trị cũ khác null và trả null, ánh xạ bị xóa.

### 8.4. compute trả null là yêu cầu loại bỏ ánh xạ

`compute` đưa null vào vị trí giá trị cũ khi không có ánh xạ hoặc có ánh xạ null. Chỉ từ tham số giá trị cũ, hàm không phân biệt được hai tình huống này.

Nếu hàm trả null, ánh xạ bị bỏ nếu có; nếu vốn chưa có thì vẫn không có. Không dùng `compute(k, ... -> null)` để “lưu một giá trị null” như `put(k, null)`.

### 8.5. merge nhận giá trị đầu vào khác null

Dù `HashMap.put(k, null)` hợp lệ, `merge(k, null, fn)` không vì thế hợp lệ. Tham số giá trị đưa vào của `merge` phải khác null.

Khi giá trị cũ null hoặc chưa có ánh xạ, `merge` gắn giá trị đầu vào khác null trực tiếp. Khi đã có giá trị khác null, nó mới dùng hàm ghép. Nếu hàm ghép trả null, ánh xạ được xóa.

Phải phân biệt ba vị trí:

1. Khóa truyền vào có thể null với `HashMap`.
2. Giá trị đầu vào của `merge` phải khác null.
3. Kết quả null từ hàm ghép có nghĩa loại bỏ ánh xạ.

Cùng một từ null nhưng vai trò khác nhau; đọc đúng vị trí tham số và kiểu hợp đồng sẽ tránh nhầm.

## 9. Chương trình đầy đủ: kiểm chứng các quy tắc cập nhật

```java
import java.util.HashMap;
import java.util.Map;

public class HashMapNullUpdateMethodsDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();
        states.put("draft", null);
        System.out.println("putIfAbsentOld="
                + states.putIfAbsent("draft", "ready"));
        System.out.println("draftNow=" + states.get("draft"));

        states.put("loadable", null);
        String loaded = states.computeIfAbsent("loadable", key -> "loaded");
        System.out.println("computeIfAbsentValue=" + loaded);

        String missingResult = states.computeIfAbsent("missing", key -> null);
        System.out.println("missingComputeResult=" + missingResult);
        System.out.println("hasMissingAfterCompute="
                + states.containsKey("missing"));

        states.put("explicit-null", null);
        String nullResult = states.computeIfAbsent("explicit-null", key -> null);
        System.out.println("existingNullComputeResult=" + nullResult);
        System.out.println("hasExplicitNullAfterComputeIfAbsent="
                + states.containsKey("explicit-null"));

        String skipped = states.computeIfPresent("explicit-null", (key, old) -> {
            throw new AssertionError("Must not run for a null value");
        });
        System.out.println("computeIfPresentResult=" + skipped);
        System.out.println("hasExplicitNullAfterComputeIfPresent="
                + states.containsKey("explicit-null"));

        states.compute("explicit-null", (key, old) -> null);
        System.out.println("hasExplicitNullAfterCompute="
                + states.containsKey("explicit-null"));

        String nullKeyValue = states.computeIfAbsent(
                null, key -> key == null ? "default" : key);
        System.out.println("computedNullKeyValue=" + nullKeyValue);

        Map<String, Integer> counts = new HashMap<>();
        counts.put("hits", null);
        System.out.println("firstMerge="
                + counts.merge("hits", 1, Integer::sum));
        System.out.println("secondMerge="
                + counts.merge("hits", 2, Integer::sum));
        System.out.println("mergeRemovalResult="
                + counts.merge("hits", 1, (old, incoming) -> null));
        System.out.println("hasHitsAfterMergeRemoval="
                + counts.containsKey("hits"));

        try {
            counts.merge("invalid", null, Integer::sum);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullMergeInput=NullPointerException");
        }
    }
}
```

Lưu thành `HashMapNullUpdateMethodsDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapNullUpdateMethodsDemo.java
java HashMapNullUpdateMethodsDemo
```

Đầu ra chính xác:

```text
putIfAbsentOld=null
draftNow=ready
computeIfAbsentValue=loaded
missingComputeResult=null
hasMissingAfterCompute=false
existingNullComputeResult=null
hasExplicitNullAfterComputeIfAbsent=true
computeIfPresentResult=null
hasExplicitNullAfterComputeIfPresent=true
hasExplicitNullAfterCompute=false
computedNullKeyValue=default
firstMerge=1
secondMerge=3
mergeRemovalResult=null
hasHitsAfterMergeRemoval=false
nullMergeInput=NullPointerException
```

### 9.1. Đang có khóa mà putIfAbsent vẫn thay giá trị

`"draft"` đã có ánh xạ null, nhưng `putIfAbsent("draft", "ready")` vẫn ghi `"ready"`. Giá trị cũ trả về là null; nó không chứng minh trước đó chưa có khóa.

### 9.2. Hai computeIfAbsent trả null nhưng sự tồn tại khác nhau

Đối với `"missing"`, hàm trả null và khóa vẫn không có. Đối với `"explicit-null"`, hàm cũng trả null nhưng khóa vẫn có ánh xạ null:

```text
hasMissingAfterCompute=false
hasExplicitNullAfterComputeIfAbsent=true
```

Sau đó `computeIfPresent` không chạy hàm cho `"explicit-null"`; thân hàm có `AssertionError` để chương trình thất bại nếu giả thiết “không chạy” bị sai.

Cuối cùng, `compute(... -> null)` xóa ánh xạ của `"explicit-null"`, nên `containsKey` thành false.

### 9.3. Hàm tính phải xử lý được khóa null nếu ứng dụng cho phép

Lời gọi `computeIfAbsent(null, ...)` dùng hàm có kiểm tra `key == null`, nên tạo giá trị `"default"` cho khóa null.

Nếu hàm thay bằng `key -> key.toUpperCase()`, ngoại lệ có thể đến từ thân hàm do gọi phương thức trên null, dù map chấp nhận khóa null. Quy tắc của container không thay thế việc kiểm tra dữ liệu trong hàm mà ứng dụng truyền vào.

### 9.4. Giá trị cũ null không được truyền vào Integer::sum ở lần merge đầu

`counts` bắt đầu với `"hits" → null`. Lần `merge` đầu nhận giá trị `1` trực tiếp, nên kết quả là `1`; không cố cộng một `Integer` null.

Lần tiếp theo có giá trị cũ `1`, ghép với `2` thành `3`. Lần sau hàm ghép trả null, xóa ánh xạ. Truyền giá trị đầu vào null cho một lần `merge` khác bị từ chối bằng `NullPointerException`.

Các hàm tính trong ví dụ không tự thêm/xóa ánh xạ của map trong lúc chạy. Hãy trả kết quả theo hợp đồng thay vì sửa chính map từ trong hàm rồi mong thao tác vẫn có ngữ nghĩa đơn giản.

## 10. Duyệt và tính toán phải xét khả năng có null

`HashMap.forEach` và các view không tự bỏ qua ánh xạ có khóa hoặc giá trị null.

Các đoạn dưới là **mẫu có thể lỗi, chỉ để phân tích**, với giả thiết map cho phép và đang chứa null:

```java
// Có thể lỗi vì key là null.
map.forEach((key, value) -> System.out.println(key.length()));

// Có thể lỗi mở hộp vì một giá trị Integer là null.
for (Integer value : stock.values()) {
    int quantity = value;
}
```

Nếu cần hiển thị, có thể dùng chuỗi thay thế chỉ cho trình bày. Nếu cần tính toán, phải quyết định null có nghĩa gì trước.

Ví dụ “số lượng chưa biết” khác với “số lượng bằng 0”. Tự đổi null thành `0` có thể làm tổng trông như đã đầy đủ dù một phần dữ liệu chưa xác định.

### getOrDefault có thể vẫn gây lỗi mở hộp

Đoạn minh họa sau cũng có thể gây `NullPointerException` nếu `"draft"` đã ánh xạ tới null:

```java
// stock là Map<String, Integer> và có "draft" -> null.
int count = stock.getOrDefault("draft", 0);
```

Giá trị dự phòng `0` không được chọn chỉ vì giá trị hiện có là null. Phương thức trả `Integer null`, sau đó phép gán cần mở hộp thành `int` và thất bại.

Khi lỗi xảy ra ở bước đọc/mở hộp này, bản thân ánh xạ null không tự bị xóa.

## 11. Chương trình đầy đủ: hiển thị và cộng phần dữ liệu đã biết

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HashMapNullPresentationDemo {
    public static void main(String[] args) {
        Map<String, Integer> stock = new HashMap<>();
        stock.put(null, null);
        stock.put("pen", 3);
        stock.put("draft", null);

        List<String> rows = new ArrayList<>();
        stock.forEach((key, value) -> {
            String keyText = Objects.toString(key, "<null-key>");
            String valueText = Objects.toString(value, "<null-value>");
            rows.add(keyText + "=" + valueText);
        });
        Collections.sort(rows);
        System.out.println("rows=" + rows);

        int knownTotal = 0;
        int unknownCount = 0;
        for (Integer value : stock.values()) {
            if (value == null) {
                unknownCount++;
            } else {
                knownTotal += value;
            }
        }
        System.out.println("knownTotal=" + knownTotal);
        System.out.println("unknownCount=" + unknownCount);

        try {
            int count = stock.get("draft");
            System.out.println("unexpectedCount=" + count);
        } catch (NullPointerException expected) {
            System.out.println("nullUnboxing=NullPointerException");
        }
        System.out.println("draftStillExists=" + stock.containsKey("draft"));
    }
}
```

Lưu thành `HashMapNullPresentationDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPresentationDemo.java
java HashMapNullPresentationDemo
```

Đầu ra chính xác:

```text
rows=[<null-key>=<null-value>, draft=<null-value>, pen=3]
knownTotal=3
unknownCount=2
nullUnboxing=NullPointerException
draftStillExists=true
```

### Vì sao các dòng được đưa vào danh sách rồi sắp xếp?

`HashMap` không bảo đảm thứ tự duyệt. Chương trình thu các dòng hiển thị vào một danh sách riêng rồi sắp xếp chuỗi để có stdout xác định.

Các nhãn `<null-key>`, `<null-value>` chỉ là cách hiển thị. Chương trình không thay khóa null thành chuỗi nhãn và không thay giá trị null trong map thành một chuỗi khác.

Trong ứng dụng thật, nhãn cần chọn sao cho người đọc hiểu. Nếu dữ liệu thật có thể chứa cùng chuỗi nhãn, cần cách trình bày phân biệt; không lấy nhãn hiển thị làm định danh dữ liệu.

### knownTotal không phải lời khẳng định mọi số lượng đều đã biết

Hai ánh xạ có giá trị null được đếm vào `unknownCount=2`; giá trị `3` góp vào `knownTotal=3`.

Tên biến và đầu ra cho biết đây là tổng của phần dữ liệu đã biết. Chúng không âm thầm giả định hai giá trị chưa biết bằng `0`.

Phần mở hộp cố ý gây lỗi ở `stock.get("draft")`. Sau khi bắt ngoại lệ, `draftStillExists=true` xác nhận việc đọc không làm ánh xạ biến mất.

## 12. Chuyển dữ liệu sang một Map khác phải kiểm tra chính sách null

Kiểu khai báo `Map<K, V>` không áp đặt mọi hiện thực phải cho khóa và giá trị null. `HashMap` có chính sách riêng đã nêu; đổi cách tạo hoặc đổi hiện thực có thể thay chính sách.

| Cách tạo hoặc loại map | Khóa/giá trị null liên quan |
|---|---|
| `new HashMap<>()` | Cho phép một khóa null, nhiều giá trị null |
| `new HashMap<>(source)` | Có thể chép các ánh xạ null hợp lệ từ một map nguồn có thật |
| `Map.of(...)` | Không chấp nhận khóa hoặc giá trị null |
| `Map.copyOf(source)` | Không chấp nhận các ánh xạ có khóa hoặc giá trị null |
| `Collections.unmodifiableMap(source)` | Là lớp bọc đọc qua nguồn; không tự xóa hay cấm các null nguồn đã có |
| `ConcurrentHashMap` | Không chấp nhận khóa hoặc giá trị null |

Không nên đọc bảng này thành việc các lựa chọn có thể thay thế nhau chỉ bằng cách đổi một dòng:

- Một map cho sửa khác với một map không cho sửa.
- Một bản chép ánh xạ khác với một lớp bọc sống.
- Chính sách null là một trục khác cần xem rõ.

### Sao chép null không có nghĩa nguồn có thể là null

`new HashMap<>(source)` có thể chép một ánh xạ khóa null hoặc giá trị null từ nguồn. Nhưng `source` vẫn phải là một map hợp lệ; việc tham số map nguồn là null là một lỗi khác với việc một entry trong nguồn mang null.

Tương tự, `putAll` vào một `HashMap` sửa được có thể chép các giá trị null từ nguồn; nó không tự bỏ qua hay lọc bỏ chúng. Nếu khóa đã có, giá trị null nguồn có thể thay giá trị trước đó ở đích.

### Không cho sửa không đồng nghĩa không có null

Một lớp bọc `unmodifiableMap` ngăn sửa ánh xạ qua lớp bọc, nhưng nếu nguồn cho null thì phép đọc qua lớp bọc vẫn có thể quan sát null. Nếu nguồn được sửa hợp lệ qua một tham chiếu khác, lớp bọc có thể thấy thay đổi đó.

Ngược lại, các factory như `Map.of` vừa tạo map không cho sửa vừa có chính sách từ chối null. Không được suy chính sách của mọi map không cho sửa chỉ từ một nhóm factory.

### Khi chuyển sang ConcurrentHashMap

Việc `ConcurrentHashMap` không cho null là khác biệt phải xử lý theo nghĩa dữ liệu. Không nên chỉ bỏ các ánh xạ null hoặc thay chúng bằng `0`, chuỗi rỗng hay một đối tượng bất kỳ nếu chưa xác định nghiệp vụ.

Có thể cần một trạng thái tường minh như “chưa tải”, “không tìm thấy”, “đã có dữ liệu”, hoặc một kiểu kết quả riêng. Bài này không thay thế thiết kế truy cập đồng thời; điểm cần nhớ là chính sách chấp nhận dữ liệu cũng thay đổi khi đổi hiện thực.

## 13. Chương trình đầy đủ: bản chép, lớp bọc và kiểm tra đầu vào

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public class HashMapNullCopyPoliciesDemo {
    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    private static void putNonNull(
            Map<String, String> target, String key, String value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        target.put(key, value);
    }

    public static void main(String[] args) {
        Map<String, String> source = new HashMap<>();
        source.put(null, "default");
        source.put("draft", null);

        Map<String, String> copied = new HashMap<>(source);
        Map<String, String> readOnly = Collections.unmodifiableMap(source);
        System.out.println("copyHasNullKey=" + copied.containsKey(null));
        System.out.println("copyHasDraft=" + copied.containsKey("draft"));
        System.out.println("copyDraftValue=" + copied.get("draft"));

        source.put("draft", "ready");
        source.put("later", null);
        System.out.println("copyDraftAfterSourceUpdate=" + copied.get("draft"));
        System.out.println("readOnlyDraft=" + readOnly.get("draft"));
        System.out.println("readOnlyHasLater=" + readOnly.containsKey("later"));

        try {
            readOnly.put("new", "value");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readOnlyPut=UnsupportedOperationException");
        }

        expectNullPointer("mapCopyOf", () -> Map.copyOf(source));
        expectNullPointer("mapOfNullValue", () -> Map.of("draft", null));
        expectNullPointer("mapOfNullKey", () -> Map.of(null, "default"));

        Map<String, String> concurrent = new ConcurrentHashMap<>();
        expectNullPointer("concurrentNullKey",
                () -> concurrent.put(null, "value"));
        expectNullPointer("concurrentNullValue",
                () -> concurrent.put("draft", null));

        Map<String, String> validated = new HashMap<>();
        putNonNull(validated, "ok", "ready");
        expectNullPointer("boundaryNullKey",
                () -> putNonNull(validated, null, "value"));
        expectNullPointer("boundaryNullValue",
                () -> putNonNull(validated, "draft", null));
        System.out.println("validatedSize=" + validated.size());
        System.out.println("validatedHasNullKey="
                + validated.containsKey(null));
        System.out.println("validatedHasNullValue="
                + validated.containsValue(null));
    }
}
```

Lưu thành `HashMapNullCopyPoliciesDemo.java`, rồi biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapNullCopyPoliciesDemo.java
java HashMapNullCopyPoliciesDemo
```

Đầu ra chính xác:

```text
copyHasNullKey=true
copyHasDraft=true
copyDraftValue=null
copyDraftAfterSourceUpdate=null
readOnlyDraft=ready
readOnlyHasLater=true
readOnlyPut=UnsupportedOperationException
mapCopyOf=NullPointerException
mapOfNullValue=NullPointerException
mapOfNullKey=NullPointerException
concurrentNullKey=NullPointerException
concurrentNullValue=NullPointerException
boundaryNullKey=NullPointerException
boundaryNullValue=NullPointerException
validatedSize=1
validatedHasNullKey=false
validatedHasNullValue=false
```

### 13.1. HashMap chép được các ánh xạ null

`copied` chứa khóa null và khóa `"draft"` có giá trị null. Sau khi nguồn thay `"draft"` thành `"ready"`, bản chép vẫn giữ ánh xạ cũ của riêng nó.

Đây là sự độc lập của cấu trúc ánh xạ, không phải sao chép sâu các đối tượng. Ví dụ dùng giá trị `String` để tránh trộn chủ đề null với việc sửa nội dung đối tượng khả biến.

### 13.2. Lớp bọc vẫn nhìn thấy nguồn

`readOnlyDraft=ready` và `readOnlyHasLater=true` vì lớp bọc đọc qua nguồn. Thử ghi qua lớp bọc bị `UnsupportedOperationException`.

Hai yếu tố này không mâu thuẫn: không cho sửa qua tham chiếu lớp bọc không phải việc chụp và đóng băng toàn bộ dữ liệu nguồn.

### 13.3. Factory và map đồng thời từ chối null

Ba phép thử `Map.copyOf`, `Map.of` và hai phép thử trên `ConcurrentHashMap` kiểm chứng các giới hạn null tương ứng.

Các hàm kiểm tra ném `AssertionError` nếu thao tác được mong là từ chối null lại chạy bình thường. Vì vậy đầu ra không chỉ là thông báo in sẵn; nó phản ánh ngoại lệ thực sự được quan sát.

### 13.4. Kiểm tra ở biên có phạm vi bảo đảm

`putNonNull` gọi `Objects.requireNonNull` trên khóa và giá trị trước khi ghi. Trong ví dụ, hai đầu vào null bị từ chối, nên map được kiểm tra còn đúng một ánh xạ hợp lệ.

Tuy nhiên, một hàm trợ giúp không tự biến mọi `HashMap` thành một loại map cấm null. Nếu nơi khác giữ tham chiếu sửa được và gọi thẳng `put`, `putAll`, `replaceAll` hoặc đổi giá trị qua entry, nó vẫn có thể ghi null.

Muốn giữ một quy tắc “không có null” cho toàn bộ ứng dụng, phải kiểm soát các đường ghi và quyền sở hữu dữ liệu. Khai báo generic `Map<String, String>` tự nó không khiến Java cấm truyền null vào vị trí khóa hay giá trị.

## 14. Chọn ý nghĩa null một cách nhất quán

Thư viện không tự quyết định null có nghĩa là “chưa nhập”, “không tồn tại”, “không áp dụng” hay “lỗi”. Nếu nhiều phần của ứng dụng tự hiểu khác nhau, cùng một ánh xạ null có thể gây các kết quả trái ngược.

Trước khi chọn biểu diễn, cần xác định:

1. Có cần phân biệt chưa có bản ghi với có bản ghi nhưng chưa có giá trị không?
2. Khóa null có một ý nghĩa nghiệp vụ duy nhất hay chỉ đang che việc thiếu định danh?
3. Có thể có nhiều bản ghi thiếu định danh cần giữ riêng không?
4. Những phép tính, hàm tải và phép ghép có đối xử với null đúng ý nghĩa ấy không?
5. Dữ liệu có được chuyển sang factory hoặc hiện thực khác có chính sách null khác không?

### Khi null có thể là biểu diễn phù hợp

Nếu một map nội bộ được sở hữu và truy cập có kiểm soát, các trạng thái được định nghĩa rõ, các đường đọc/xử lý đều xét đầy đủ và việc dùng null không làm mất dữ liệu cần phân biệt, nó có thể là một lựa chọn biểu diễn.

Ví dụ, trạng thái “đã có bản ghi nhưng chưa nhập mô tả” có thể được phân biệt với “chưa có bản ghi” bằng sự tồn tại của khóa, nếu đây là chính sách đã được thống nhất.

### Khi nên biểu diễn trạng thái tường minh

Nếu có nhiều lý do chưa có giá trị hoặc nhiều bước chuyển trạng thái, một null duy nhất có thể không đủ thông tin. Một kiểu dữ liệu có trường trạng thái hoặc một kiểu kết quả riêng thường giúp chương trình diễn đạt đúng hơn.

Không thay null bằng chuỗi rỗng, `0` hoặc một khóa đặc biệt một cách máy móc: các giá trị ấy có thể đã là dữ liệu thật hợp lệ. Mỗi cách thay cần quy tắc để tránh làm hai trạng thái khác nhau trở thành một.

Một khóa enum hoặc kiểu khóa có tên ý nghĩa đôi khi diễn đạt vai trò “mặc định” rõ hơn null. Nhưng lựa chọn phải theo dữ liệu và cách sử dụng, không phải chỉ để tránh nhìn thấy từ null trong mã.

## 15. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể gặp | Cách xử lý đúng ý nghĩa |
|---|---|---|
| Nhiều bản ghi thiếu mã chỉ còn bản ghi cuối | Tất cả dùng cùng khóa null | Giữ định danh riêng hoặc đổi cấu trúc theo nghiệp vụ |
| `get` trả null rồi kết luận khóa không có | Bỏ qua khả năng giá trị null | Kiểm tra sự tồn tại khi cần phân biệt |
| `getOrDefault` vẫn trả null | Khóa có ánh xạ null | Chọn quy tắc dự phòng rõ ràng |
| `remove` trả null rồi kết luận không xóa gì | Giá trị cũ có thể là null | Ghi nhận thông tin tồn tại theo cơ chế truy cập phù hợp |
| `compute(... -> null)` làm mất khóa | Null là tín hiệu xóa trong phương thức này | Dùng đúng API nếu muốn lưu giá trị null |
| `merge(k, null, fn)` ném ngoại lệ | Tham số đầu vào này bắt buộc khác null | Không suy chính sách `put` cho mọi phương thức |
| Đọc số lượng bị NullPointerException | Mở hộp `Integer null` | Xử lý null trước phép tính |
| Chuyển sang `Map.copyOf` bị lỗi | Nguồn có khóa/giá trị null | Thiết kế cách chuyển trạng thái hoặc chọn cấu trúc phù hợp |
| Lớp bọc không cho sửa vẫn thấy null | Hạn chế sửa và chính sách null là hai trục | Hiểu lớp bọc đọc qua nguồn, không tự làm sạch dữ liệu |

## 16. Tự kiểm tra

### Câu 1: Ba lần ghi khóa null

Map rỗng lần lượt `put(null, "A")`, `put(null, "B")`, `put(null, "C")`. Kích thước và giá trị hiện tại của khóa null là gì?

**Đáp án:** Kích thước `1`, giá trị `"C"`. Ba lần ghi cùng khóa không tạo ba ánh xạ.

### Câu 2: Ba khóa khác nhau, cùng giá trị null

Map rỗng ghi `"a" → null`, `"b" → null`, `"c" → null`. Size là bao nhiêu? Có vi phạm tính duy nhất không?

**Đáp án:** Size là `3`. Khóa khác nhau; giá trị được phép lặp nên không vi phạm.

### Câu 3: null và "null"

Map có khóa null và khóa chuỗi `"null"`. Chúng có bắt buộc là một khóa không?

**Đáp án:** Không. Chuỗi `"null"` là đối tượng có nội dung; null là tham chiếu không có đối tượng.

### Câu 4: get(null) trả null

Có thể kết luận không có khóa null không?

**Đáp án:** Không. Có thể đang có ánh xạ `null → null`. Dùng `containsKey(null)` khi cần phân biệt sự tồn tại, trong một cơ chế truy cập phù hợp.

### Câu 5: Có ánh xạ null và giá trị dự phòng

Khóa `"draft"` tồn tại với giá trị null. `getOrDefault("draft", "fallback")` trả gì?

**Đáp án:** Null. Giá trị dự phòng được dùng khi không có ánh xạ, không tự thay mọi null.

### Câu 6: Xóa trả null

Khóa tồn tại với giá trị null, rồi `remove(k)` trả null. Có thể phép xóa đã làm size giảm không?

**Đáp án:** Có. Giá trị cũ được trả ra là null; ánh xạ vẫn có thể vừa được loại bỏ.

### Câu 7: computeIfAbsent và compute

Khóa đang có ánh xạ null. Hai lời gọi riêng trong hai tình huống độc lập là `computeIfAbsent(k, x -> null)` và `compute(k, (x, old) -> null)`. Sự tồn tại của khóa sau đó khác nhau thế nào?

**Đáp án:** Lời gọi đầu giữ ánh xạ null đã có; lời gọi thứ hai xóa ánh xạ. Không thể diễn giải mọi kết quả null từ hàm tính như cùng một tín hiệu.

### Câu 8: putIfAbsent

Khóa đã có nhưng giá trị null. `putIfAbsent(k, "ready")` có thể ghi `"ready"` không?

**Đáp án:** Có. Phương thức xét cả trường hợp đang ánh xạ tới null, không chỉ trường hợp `containsKey` là false.

### Câu 9: merge với đầu vào null

`HashMap` cho null value, vậy `merge(k, null, fn)` có được chấp nhận chỉ vì điều đó không?

**Đáp án:** Không. Giá trị đầu vào của `merge` phải khác null. Cần đọc hợp đồng của từng phương thức.

### Câu 10: Xóa null qua values

Có ba ánh xạ giá trị null. Một lần `values().remove(null)` có chắc xóa cả ba không?

**Đáp án:** Không. Nó xóa một lần xuất hiện phù hợp nếu có. Muốn lọc hết phải thực hiện một phép lọc tương ứng và chấp nhận việc bỏ các ánh xạ đó.

### Câu 11: Không cho sửa có nghĩa không null?

Một lớp bọc `Collections.unmodifiableMap` trên `HashMap` có null. Phép đọc qua lớp bọc có thể trả null không?

**Đáp án:** Có. Lớp bọc không tự lọc hoặc thay null; nó ngăn sửa ánh xạ qua tham chiếu lớp bọc.

### Câu 12: Đếm số lượng chưa biết

Map chứa `"pen" → 3`, `"draft" → null`. Có được kết luận tổng số lượng thật bằng `3` nếu null có nghĩa “chưa biết” không?

**Đáp án:** Chỉ biết tổng phần đã biết là `3`. Còn một giá trị chưa xác định; không tự biến nó thành số `0` nếu nghiệp vụ chưa quy định.

## 17. Thực hành: giữ đủ trạng thái khi đọc

Viết một chương trình dùng `HashMap<String, Integer>` và tạo:

```text
null    → 5
"draft" → null
"ready" → 8
```

Thực hiện:

1. Đếm số ánh xạ, số khóa null và số giá trị null.
2. Đọc `"draft"` và một khóa `"missing"` chưa có; in cả giá trị lẫn sự tồn tại.
3. So kết quả `getOrDefault` của hai khóa đó với cùng một số dự phòng.
4. Thay giá trị khóa null thành null; đếm lại null values.
5. Xóa riêng `"draft"` và giải thích vì sao kết quả trả về có thể null dù size giảm.
6. Thu các dòng để hiển thị theo một thứ tự xác định mà không giả định thứ tự HashMap.
7. Thử sao chép bằng `new HashMap<>(source)` và so chính sách với `Map.copyOf(source)`.

Các mốc cần đạt:

```text
Ban đầu: size = 3, null keys = 1, null values = 1.
draft tồn tại; missing không tồn tại.
get của cả hai có thể cùng trả null.
getOrDefault chỉ dùng dự phòng cho missing.
Sau khi put(null, null): null values = 2, size vẫn = 3.
Sau khi remove("draft"): size = 2, còn khóa null.
```

Cuối cùng viết rõ một lựa chọn nghiệp vụ:

- Nếu null mang trạng thái có ý nghĩa, mô tả cách mọi đường đọc giữ sự khác nhau với thiếu khóa.
- Nếu ứng dụng cấm null, chỉ ra nơi kiểm tra và cách ngăn các đường ghi khác bỏ qua quy tắc.
- Nếu cần nhiều trạng thái thiếu giá trị, đề xuất một biểu diễn có tên trạng thái rõ thay vì gộp tất cả vào null.

Mục tiêu là bảo toàn thông tin dữ liệu và dùng API theo đúng hợp đồng, không chỉ làm cho chương trình hết ném ngoại lệ.

## Tài liệu đối chiếu

- [Java 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hỗ trợ khóa/giá trị null và các phương thức cập nhật.
- [Java 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): phân biệt thiếu ánh xạ với giá trị null; `getOrDefault`, `compute`, `merge` và các factory không chấp nhận null.
- [Java 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): hiển thị tham chiếu null và kiểm tra đầu vào bằng `requireNonNull`.
- [Java 17 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): lớp bọc không cho sửa đọc qua map nguồn.
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): chính sách không chấp nhận khóa hoặc giá trị null.

Năm chương trình độc lập dùng API tương thích Java 17 trở lên, đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2. Các khối đầu ra là kết quả thực tế; không phụ thuộc vào thứ tự duyệt không được bảo đảm của `HashMap`.
