# Tạo, truy cập và cập nhật EnumMap

## 1. Một bảng ánh xạ có miền khóa là enum

`EnumMap<K, V>` là một kiểu `Map` chuyên dùng khi mọi khóa thuộc cùng một kiểu enum `K`. Giá trị `V` không bắt buộc là enum; nó có thể là số đếm, cấu hình, danh sách công việc hoặc một kiểu đối tượng phù hợp.

Ví dụ một bộ đếm theo kênh gửi:

```java
enum Channel {
    EMAIL, SMS, PUSH
}

EnumMap<Channel, Integer> counts = new EnumMap<>(Channel.class);
```

Trong đoạn minh họa, enum là một khai báo kiểu, còn câu lệnh tạo map đặt trong một phương thức hoặc phần khởi tạo phù hợp. `Channel.class` cung cấp kiểu khóa cho map, kể cả khi map đang rỗng.

Map mới chưa có ánh xạ nào. Nó không tự tạo một giá trị cho mỗi hằng enum và cũng không tự mặc định mọi khóa thành 0. Có enum `EMAIL` không đồng nghĩa `counts.containsKey(Channel.EMAIL)` đã là `true`.

`EnumMap` không phải một mảng để người gọi phải tự chỉ số hóa bằng `ordinal()`. Người gọi dùng các hằng enum có kiểu rõ ràng làm khóa qua API `Map`.

Hợp đồng tổng quan được nêu tại [EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html). Các ví dụ trong bài dùng Java hiện hành và chạy bằng JDK 17 trở lên.

## 2. Tạo map đúng kiểu khóa

### 2.1. Tạo rỗng bằng Class của enum

```java
EnumMap<Channel, Integer> counts = new EnumMap<>(Channel.class);
```

Đây là cách rõ ràng khi bắt đầu từ một map rỗng hoặc khi nguồn dữ liệu có thể rỗng. Kiểu khóa đã được cung cấp trực tiếp; `V` được chọn là `Integer` để lưu giá trị số theo hợp đồng generic.

Nếu muốn có một giá trị 0 cho mọi kênh, phải thêm các ánh xạ có chủ đích:

```java
for (Channel channel : Channel.values()) {
    counts.put(channel, 0);
}
```

Việc map có đủ mọi khóa hay chỉ giữ các khóa phát sinh là một quyết định dữ liệu. Hai mô hình có thể cho cùng một kết quả hiển thị 0 nhưng khác nhau về `containsKey`, kích thước và ý nghĩa “chưa có dữ liệu”.

### 2.2. Tạo từ một EnumMap khác

```java
EnumMap<Channel, Integer> copied = new EnumMap<>(counts);
```

Map mới có cùng kiểu khóa và các ánh xạ ban đầu. Sau đó thêm/xóa/thay một ánh xạ ở `copied` không tự cập nhật `counts`.

Nếu giá trị là một đối tượng có thể sửa như `List<String>`, bản sao map vẫn có thể chia sẻ tham chiếu giá trị với nguồn. Sao chép các ánh xạ không phải sao chép sâu đối tượng giá trị.

Kiểu khóa được nguồn `EnumMap` giữ lại kể cả khi nguồn rỗng, nên dạng khởi tạo này dùng được với một `EnumMap` rỗng.

### 2.3. Tạo từ Map tổng quát

Constructor nhận `Map` có thể suy ra kiểu enum từ khóa của nguồn không rỗng. Nếu nguồn không phải một `EnumMap` và không có ánh xạ nào, constructor không có khóa để xác định miền enum và ném `IllegalArgumentException`.

Khi nguồn tổng quát có thể rỗng, tạo rỗng theo kiểu rồi thêm ánh xạ:

```java
EnumMap<Channel, Integer> result = new EnumMap<>(Channel.class);
result.putAll(source);
```

Trong đoạn này, `source` là một `Map<Channel, Integer>` phù hợp. Nguồn rỗng vẫn hợp lệ với cách khởi tạo có kiểu rõ; nguồn `null`, khóa không hợp lệ hoặc các giá trị trái với chính sách ứng dụng vẫn cần xử lý riêng.

## 3. Đọc và ghi cơ bản

| Thao tác | Tác dụng | Giá trị trả về cần hiểu |
| --- | --- | --- |
| `put(key, value)` | Thêm mới hoặc thay giá trị của khóa | Giá trị trước đó, hoặc `null` trong các trường hợp tương ứng |
| `get(key)` | Đọc giá trị hiện tại | Có thể là `null` nếu không có khóa hoặc có ánh xạ tới null |
| `containsKey(key)` | Kiểm tra sự tồn tại ánh xạ theo khóa | `true`/`false`, không phụ thuộc giá trị có bằng null hay không |
| `getOrDefault(key, defaultValue)` | Dùng giá trị mặc định khi khóa vắng | Không thay đổi map |
| `remove(key)` | Xóa ánh xạ nếu có | Giá trị trước đó, có thể là `null` |
| `clear()` | Xóa mọi ánh xạ | Không trả lại một map mới |

Một khóa chỉ có tối đa một giá trị. Gọi `put` lần nữa với cùng hằng enum không tạo “bản ghi trùng khóa”; nó thay giá trị của ánh xạ hiện tại.

```java
Integer previous = counts.put(Channel.EMAIL, 5);
Integer current = counts.get(Channel.EMAIL);
```

`previous` giúp quan sát giá trị bị thay, nhưng một kết quả `null` chưa đủ phân biệt “trước đó chưa có khóa” với “trước đó có giá trị null”. Nếu phân biệt này quan trọng, kiểm tra sự tồn tại theo hợp đồng phù hợp.

## 4. Khóa vắng khác khóa có giá trị null

`EnumMap` không nhận khóa `null`, nhưng cho phép giá trị `null`. Vì vậy hai trường hợp sau khác nhau:

```java
EnumMap<Channel, Integer> counts = new EnumMap<>(Channel.class);
counts.put(Channel.PUSH, null);
```

| Biểu thức | Kết quả trong ví dụ |
| --- | --- |
| `counts.get(Channel.PUSH)` | `null` |
| `counts.containsKey(Channel.PUSH)` | `true` |
| `counts.get(Channel.SMS)` | `null` |
| `counts.containsKey(Channel.SMS)` | `false` |
| `counts.getOrDefault(Channel.PUSH, 0)` | `null` |
| `counts.getOrDefault(Channel.SMS, 0)` | `0` |

`getOrDefault` chỉ sử dụng giá trị mặc định khi khóa vắng; nó không tự thay một giá trị null đã được lưu bằng 0.

Nếu gán kết quả `get` vào một biến `int`, Java phải mở hộp `Integer`. Kết quả null có thể gây `NullPointerException`. Với một map số đếm, thường nên có quy tắc rõ rằng giá trị hợp lệ không null, nhưng đó là chính sách của ứng dụng cần được thực thi, không phải điều `EnumMap` tự áp đặt.

`put(null, value)` bị từ chối bằng `NullPointerException`. Enum làm khóa giúp có miền khóa hữu hạn có kiểu, không biến `null` thành một hằng khóa hợp lệ.

## 5. Chọn thao tác cập nhật theo ý định

### 5.1. putIfAbsent: chỉ khởi tạo khi chưa có giá trị khác null

```java
counts.putIfAbsent(Channel.EMAIL, 0);
```

Phương thức này giữ nguyên một giá trị đã có và khác null. Nếu khóa vắng hoặc đang ánh xạ tới null, nó có thể ghi giá trị được cung cấp.

Đừng đọc tên “Absent” rồi giả định nó chỉ quan tâm đến `containsKey == false`. Với một map cho phép giá trị null, cần đọc đúng hợp đồng null của thao tác.

### 5.2. replace: thay khi đã có ánh xạ

```java
counts.replace(Channel.SMS, 4);
boolean changed = counts.replace(Channel.EMAIL, 6, 7);
```

Dạng hai đối số không thêm một khóa đang vắng. Dạng ba đối số chỉ thay khi khóa hiện tại có giá trị phù hợp với giá trị cũ được yêu cầu; giá trị boolean cho biết phép thay có diễn ra.

Đây là cập nhật theo điều kiện của API `Map`, không tự là một thao tác đồng bộ nguyên tử an toàn cho nhiều luồng trên `EnumMap`.

### 5.3. merge: gộp số đếm hoặc kết quả

```java
counts.merge(Channel.EMAIL, 1, Integer::sum);
```

Nếu chưa có giá trị khác null, map nhận giá trị 1. Nếu đã có một số đếm, hàm gộp nhận giá trị cũ và giá trị được đưa vào để tạo kết quả mới.

Giá trị đưa vào `merge` phải khác null theo hợp đồng phương thức, dù bản thân `EnumMap` cho phép lưu null qua `put`. Nếu hàm gộp trả null, ánh xạ bị xóa; không coi đó là yêu cầu lưu một giá trị null.

`merge` giúp mô tả rõ ý định gộp thay vì tự viết chuỗi `get` rồi tính rồi `put`. Nó vẫn không làm `EnumMap` trở thành một map đồng thời.

Tham khảo [Map.merge](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)).

### 5.4. computeIfAbsent: tạo đối tượng giá trị khi cần

Một ví dụ nhóm công việc theo kênh:

```java
EnumMap<Channel, List<String>> jobs = new EnumMap<>(Channel.class);
jobs.computeIfAbsent(Channel.EMAIL, key -> new ArrayList<>()).add("job-1");
```

Khi chưa có giá trị khác null cho khóa, hàm tạo danh sách được dùng để cung cấp giá trị. Lời gọi sau với cùng khóa có danh sách khác null sẽ nhận lại danh sách đang có, rồi thêm công việc vào đó.

Nếu hàm ánh xạ trả null, `computeIfAbsent` không tạo ánh xạ mới bằng kết quả ấy. Tránh sửa chính map một cách vòng lại trong hàm ánh xạ; giữ callback tập trung vào việc tính/tạo giá trị.

Lệnh `.add(...)` ở cuối sửa trạng thái danh sách giá trị. Nếu có một bản sao map vẫn trỏ tới cùng danh sách, thay đổi đó có thể được quan sát qua cả hai map.

Xem [Map.computeIfAbsent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#computeIfAbsent(K,java.util.function.Function)).

## 6. Chương trình chạy đầy đủ

Lưu thành `EnumMapOperationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public class EnumMapOperationsDemo {
    enum Channel {
        EMAIL, SMS, PUSH
    }

    public static void main(String[] args) {
        EnumMap<Channel, Integer> counts = new EnumMap<>(Channel.class);
        System.out.println("initial size=" + counts.size());

        Integer firstPrevious = counts.put(Channel.EMAIL, 2);
        Integer secondPrevious = counts.put(Channel.EMAIL, 5);
        System.out.println("first previous=" + firstPrevious);
        System.out.println("second previous=" + secondPrevious);
        System.out.println("email count=" + counts.get(Channel.EMAIL));

        counts.put(Channel.PUSH, null);
        System.out.println("push present=" + counts.containsKey(Channel.PUSH));
        System.out.println("push default="
                + counts.getOrDefault(Channel.PUSH, 0));
        System.out.println("sms default="
                + counts.getOrDefault(Channel.SMS, 0));

        counts.merge(Channel.EMAIL, 1, Integer::sum);
        counts.merge(Channel.SMS, 1, Integer::sum);
        counts.putIfAbsent(Channel.PUSH, 0);
        counts.replace(Channel.SMS, 4);
        boolean changed = counts.replace(Channel.EMAIL, 6, 7);
        System.out.println("conditional replacement=" + changed);
        System.out.println("updated counts=" + counts);

        Integer removed = counts.remove(Channel.PUSH);
        System.out.println("removed push=" + removed);
        System.out.println("after removal=" + counts);

        EnumMap<Channel, List<String>> jobs = new EnumMap<>(Channel.class);
        jobs.computeIfAbsent(Channel.EMAIL, key -> new ArrayList<>()).add("job-1");
        jobs.computeIfAbsent(Channel.EMAIL, key -> new ArrayList<>()).add("job-2");
        System.out.println("email jobs=" + jobs.get(Channel.EMAIL));

        EnumMap<Channel, Integer> copied = new EnumMap<>(counts);
        copied.put(Channel.EMAIL, 99);
        System.out.println("source email=" + counts.get(Channel.EMAIL));
        System.out.println("copied email=" + copied.get(Channel.EMAIL));

        EnumMap<Channel, Integer> emptyEnumMap = new EnumMap<>(Channel.class);
        System.out.println("copy empty enum map size="
                + new EnumMap<>(emptyEnumMap).size());

        Map<Channel, Integer> emptyGenericMap = Map.of();
        try {
            new EnumMap<>(emptyGenericMap);
        } catch (IllegalArgumentException expected) {
            System.out.println("copy empty generic map=rejected");
        }
        EnumMap<Channel, Integer> typedCopy = new EnumMap<>(Channel.class);
        typedCopy.putAll(emptyGenericMap);
        System.out.println("typed empty copy size=" + typedCopy.size());

        try {
            counts.put(null, 1);
        } catch (NullPointerException expected) {
            System.out.println("null key=rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumMapOperationsDemo.java
java EnumMapOperationsDemo
```

Stdout:

```text
initial size=0
first previous=null
second previous=2
email count=5
push present=true
push default=null
sms default=0
conditional replacement=true
updated counts={EMAIL=7, SMS=4, PUSH=0}
removed push=0
after removal={EMAIL=7, SMS=4}
email jobs=[job-1, job-2]
source email=7
copied email=99
copy empty enum map size=0
copy empty generic map=rejected
typed empty copy size=0
null key=rejected
```

Phần `PUSH` minh họa ánh xạ null được `putIfAbsent` khởi tạo lại thành 0. Hai bước `merge` tạo hoặc cộng số; `replace` sau đó chỉ thay theo hợp đồng riêng của nó.

Thứ tự in các khóa là thứ tự khai báo enum `EMAIL, SMS, PUSH`, không phải lịch sử gọi `put`. `EnumMap` chỉ in những khóa đang có ánh xạ, kể cả khi một giá trị của chúng bằng null.

## 7. Giữ hợp đồng của map rõ ràng

### Đừng giả định có ánh xạ cho mọi hằng

Một `EnumMap` có kiểu khóa `Channel` không có nghĩa cả ba kênh đều được khởi tạo. Nếu thuật toán yêu cầu cấu hình cho mọi hằng, hãy thêm và xác thực các ánh xạ cần thiết trước khi dùng.

Nếu chỉ lưu những kênh đã phát sinh dữ liệu, giữ sự khác nhau giữa khóa vắng và giá trị 0 khi nó có ý nghĩa. Không để một lần gọi `getOrDefault` làm người đọc tưởng rằng map đã thực sự chứa khóa đó.

### Phân biệt thay giá trị và sửa đối tượng giá trị

`map.put(key, anotherList)` thay ánh xạ sang một đối tượng danh sách khác. `map.get(key).add(item)` giữ ánh xạ nhưng sửa đối tượng danh sách đang có, và có thể lỗi nếu khóa vắng hoặc danh sách không cho sửa.

Một constructor sao chép map tạo vùng ánh xạ riêng, nhưng không mặc định sao chép sâu những danh sách bên trong. Nếu cần cô lập dữ liệu giá trị, phải thiết kế bước sao chép hoặc dùng các giá trị bất biến phù hợp.

### Không dùng ordinal làm API truy cập bên ngoài

Một trong các lợi ích của `EnumMap` là người gọi dùng khóa enum trực tiếp. Không cần tự xây mảng theo `ordinal()` rồi thay map bằng những chỉ số có thể bị diễn giải sai khi enum đổi.

Nếu enum đi qua biên trao đổi/lưu trữ, việc chuyển từ mã dữ liệu bên ngoài sang enum là trách nhiệm riêng. `EnumMap` không tự biến một chuỗi tùy ý thành khóa hợp lệ.

### Không suy ra an toàn luồng từ các phương thức cập nhật gọn

`EnumMap` không tự đồng bộ hóa. Những tên `putIfAbsent`, `merge` hoặc `computeIfAbsent` không biến mọi chuỗi cập nhật trên nó thành giao dịch nguyên tử cho nhiều luồng.

Nếu nhiều luồng chia sẻ dữ liệu, cần một thiết kế khóa hoặc cấu trúc đồng thời thích hợp, gồm cả cách bảo vệ đối tượng giá trị có thể sửa. Chọn kiểu map chuyên dụng theo enum và chọn giao thức đồng thời là hai quyết định khác nhau.

## 8. Tự kiểm tra

1. `new EnumMap<>(Channel.class)` có tự tạo giá trị 0 cho mọi hằng không?
2. `put` cùng một khóa lần thứ hai tạo thêm ánh xạ hay thay giá trị?
3. Vì sao `get(key) == null` chưa đủ kết luận khóa vắng?
4. `getOrDefault` có đổi giá trị null đang được lưu thành mặc định không?
5. Khi nguồn là một Map tổng quát có thể rỗng, nên tạo EnumMap theo cách nào?
6. `computeIfAbsent` trả về danh sách rồi `.add` có đang thay một ánh xạ mới mỗi lần không?

Đáp án:

1. Không. Nó tạo map rỗng với kiểu khóa đã biết.
2. Thay giá trị của ánh xạ cùng khóa và có thể trả về giá trị trước đó.
3. Vì EnumMap cho phép khóa hiện diện với giá trị null; dùng containsKey khi cần phân biệt.
4. Không. Chỉ dùng mặc định khi khóa không có ánh xạ.
5. Tạo bằng Class của enum rồi putAll nguồn, thay vì đòi constructor suy kiểu từ nguồn rỗng không phải EnumMap.
6. Không. Khi đã có danh sách khác null, nó dùng lại danh sách đó; `.add` sửa đối tượng danh sách.

Hãy xác định kiểu khóa lúc tạo, chính sách khóa vắng/null lúc đọc và ý định thêm/thay/gộp lúc cập nhật. Những quyết định này giúp dùng EnumMap đúng như một bảng ánh xạ có hợp đồng rõ.
