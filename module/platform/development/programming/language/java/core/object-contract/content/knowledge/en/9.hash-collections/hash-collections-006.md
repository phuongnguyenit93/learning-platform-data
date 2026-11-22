# Va chạm hash không tự nó làm mất tính đúng đắn

## Mục tiêu

Một cấu trúc dữ liệu băm như `HashMap` hoặc `HashSet` dùng mã băm để tìm nơi lưu trữ và tra cứu phần tử hiệu quả. Nhiều đối tượng có thể cho cùng mã băm (**hash collision**, va chạm băm). Tuy nhiên, **collision tự nó không khiến `HashMap` nhầm hai khóa khác nhau thành một khóa hoặc khiến `HashSet` đánh mất phần tử**.

Sau bài này, bạn sẽ hiểu:

- Collision là gì và vì sao không thể đòi hỏi mọi đối tượng khác nhau đều phải có hash khác nhau.
- Cơ chế khái niệm mà cấu trúc dữ liệu băm dùng để xử lý nhiều khóa cùng mã băm.
- Vai trò riêng của `hashCode()` và `equals()` trong quyết định tìm được khóa, thay thế giá trị hay cho phép thêm phần tử.
- Cách kiểm chứng bằng Java 17+ rằng nhiều khóa cùng hash vẫn được lưu và truy xuất đúng.
- Sự khác biệt giữa **đúng đắn về kết quả** và **hiệu năng**; các lỗi hợp đồng hoặc thay đổi khóa có thể thực sự gây vấn đề.

## 1. Collision là gì?

Hàm `hashCode()` của Java trả về `int`, một giá trị số nguyên có dấu 32 bit. Số đối tượng và trạng thái dữ liệu có thể tạo ra lớn hơn rất nhiều tập mã băm hữu hạn đó. Vì thế, không thể bảo đảm một mã băm độc nhất cho mọi đối tượng.

**Hash collision** xảy ra khi hai đối tượng hoặc khóa **khác nhau về phép so sánh bằng nhau** nhưng cho cùng mã băm:

```text
a.equals(b) == false
a.hashCode() == b.hashCode()
```

Đây là tình huống **hợp lệ**. Ví dụ tưởng tượng, nếu mã băm của khóa số là chữ số hàng đơn vị, khóa 21 và khóa 31 đều có hash 1 nhưng vẫn là hai khóa khác nhau. Cách băm đó có thể phân bố kém, song collision không làm biến mất thông tin gốc về khóa.

Ngay cả những hàm băm được thiết kế tốt vẫn có thể collision. Điều quan trọng là cấu trúc lưu trữ biết cách **phân biệt các khóa va chạm** thay vì dùng mỗi mã băm làm bằng chứng hai khóa bằng nhau.

### Nhắc lại hợp đồng liên quan

Với các đối tượng tuân thủ hợp đồng `equals()/hashCode()`:

| Quan hệ | Có bắt buộc không? |
| --- | --- |
| `a.equals(b) == true` ⇒ `a.hashCode() == b.hashCode()` | **Bắt buộc** |
| `a.hashCode() == b.hashCode()` ⇒ `a.equals(b) == true` | **Không** |
| `a.equals(b) == false` ⇒ hai hash phải khác nhau | **Không** |

Điều kiện đầu tiên bảo đảm những khóa bằng nhau về logic có mã băm tương thích để cấu trúc băm có thể tìm và đối chiếu chúng. Hai điều kiện còn lại cho phép collision.

## 2. Mã băm giúp tìm ứng viên, `equals()` quyết định bằng nhau

Trong `HashMap<K,V>`, hàm băm giúp xác định vùng tìm kiếm ứng viên. Khi có nhiều khóa va chạm, triển khai vẫn phải tìm ra khóa nào **thực sự bằng khóa cần tra cứu**. Việc xác định bằng nhau có thể tận dụng kiểm tra cùng tham chiếu rồi gọi `equals()` khi cần. Chỉ có cùng mã băm chưa đủ.

Mô hình tư duy:

```text
                 map.get(key)
                     │
                     ▼
            Tính hash của key
                     │
                     ▼
       Xác định vùng chứa ứng viên
                     │
                     ▼
    Đối chiếu từng ứng viên thích hợp
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
      Khóa bằng nhau         Khóa khác nhau
      theo equals()          dù hash có thể trùng
          │                     │
          ▼                     ▼
   Trả về giá trị         Tiếp tục tìm hoặc
   tương ứng              kết luận không có
```

Đây là **sơ đồ khái niệm**, không phải bản sao mã nguồn nội bộ của một phiên bản `HashMap`. Tùy triển khai, bảng có thể xử lý thêm bit của hash, dùng các nhóm chứa nhiều mục nhập, và tổ chức nhóm bằng danh sách hoặc cây khi phù hợp. Cơ chế cụ thể ảnh hưởng chủ yếu đến cách tìm kiếm và hiệu năng. Ngữ nghĩa của `Map` vẫn đòi hỏi phân biệt khóa không bằng nhau.

Với `HashSet`, nguyên lý tương tự: một phần tử chỉ bị coi là đã tồn tại nếu có phần tử **bằng nó** theo quy tắc của tập hợp. Hai phần tử khác nhau nhưng cùng hash được phép cùng tồn tại.

### Minh họa một vùng va chạm

Giả sử ba khóa có hash là 5, nhưng chỉ `A` và `A2` bằng nhau:

```text
Nhóm có hash 5:

  [Key A, value 100]    [Key B, value 200]

Key A.equals(Key B)  = false  → hai mục nhập
Key A.equals(Key A2) = true   → A2 là khóa tương đương A
```

Nếu `put(A2, 300)`, thao tác cập nhật mục nhập dành cho khóa `A`, chứ không tạo thêm khóa thứ ba chỉ vì `A2` là một instance mới. Nếu `put(B, 400)`, dữ liệu của `A` vẫn độc lập dù `B` có cùng hash. Trùng hash có thể khiến việc tìm ứng viên lâu hơn, nhưng không biến `B` thành `A`.

## 3. Ví dụ Java 17+ chạy được: mọi khóa đều có cùng hash

Ta cố ý tạo một lớp khóa có hàm `hashCode()` luôn trả về `1` để mô phỏng tình huống va chạm cực đoan. Lớp này sử dụng `record` trong Java 17: phép `equals()` được sinh ra để so sánh giá trị thành phần `id`, còn `hashCode()` được ghi đè rõ ràng thành một giá trị cố định.

Đây là **mẫu để quan sát hành vi**, không phải khuyến nghị thiết kế hàm băm cho ứng dụng thật.

Tạo tệp `HashCollisionCorrectnessDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCollisionCorrectnessDemo {
    record Key(int id) {
        @Override
        public int hashCode() {
            return 1; // Cố ý tạo collision cho tất cả khóa
        }
    }

    public static void main(String[] args) {
        Key a = new Key(10);
        Key b = new Key(20);
        Key equivalentA = new Key(10);

        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different keys: " + !a.equals(b));
        System.out.println("equal keys: " + a.equals(equivalentA));

        Map<Key, String> map = new HashMap<>();
        map.put(a, "ten");
        map.put(b, "twenty");

        System.out.println("map size: " + map.size());
        System.out.println("get 10: " + map.get(new Key(10)));
        System.out.println("get 20: " + map.get(new Key(20)));
        System.out.println("get 99: " + map.get(new Key(99)));

        String previous = map.put(equivalentA, "TEN");
        System.out.println("previous: " + previous);
        System.out.println("map size after update: " + map.size());
        System.out.println("get 10 after update: "
                + map.get(new Key(10)));
        System.out.println("get 20 after update: "
                + map.get(new Key(20)));

        Set<Key> set = new HashSet<>();
        set.add(a);
        set.add(b);
        boolean addedEquivalent = set.add(equivalentA);

        System.out.println("set size: " + set.size());
        System.out.println("added equal key: " + addedEquivalent);
        System.out.println("set contains 20: "
                + set.contains(new Key(20)));
        System.out.println("set contains 99: "
                + set.contains(new Key(99)));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac HashCollisionCorrectnessDemo.java
java HashCollisionCorrectnessDemo
```

**Đầu ra chính xác:**

```text
same hash: true
different keys: true
equal keys: true
map size: 2
get 10: ten
get 20: twenty
get 99: null
previous: ten
map size after update: 2
get 10 after update: TEN
get 20 after update: twenty
set size: 2
added equal key: false
set contains 20: true
set contains 99: false
```

Giải thích từng nhóm kết quả:

1. `a` và `b` có cùng hash `1`, nhưng `record Key(int id)` có `equals()` dựa trên `id`, vì thế `a.equals(b)` là `false`.
2. Hai lần gọi `map.put(a, ...)` và `map.put(b, ...)` lưu **hai khóa riêng**; `map.size()` là `2`, không phải `1`.
3. `map.get(new Key(10))` tìm lại giá trị `"ten"` dù đối tượng truy vấn vừa được tạo, vì khóa truy vấn bằng `a` theo `equals()`. Tương tự với `Key(20)`.
4. `map.get(new Key(99))` là `null` vì không có khóa tương đương; việc hash của `Key(99)` cũng bằng `1` **không làm chương trình lấy nhầm giá trị** của khóa khác.
5. `map.put(equivalentA, "TEN")` thay giá trị của khóa `Key(10)`, trả lại giá trị trước đó là `"ten"`. Số khóa vẫn là `2`, và giá trị của `Key(20)` vẫn là `"twenty"`.
6. `HashSet` lưu hai phần tử `Key(10)` và `Key(20)`. Thêm `equivalentA` thất bại vì đã có phần tử bằng nó, không phải vì collision. Sau đó `contains(Key(20))` đúng, còn `contains(Key(99))` sai.

Chương trình chỉ in các phép truy vấn đã xác định, không dựa vào thứ tự duyệt `HashMap`/`HashSet`. Nhờ vậy đầu ra rõ ràng và không phụ thuộc thứ tự của cấu trúc băm.

## 4. Vì sao hàm hash cố định vẫn đúng về logic?

Hàm `hashCode()` luôn trả về `1` thỏa những điều kiện cốt lõi của hợp đồng:

- Trên cùng đối tượng với dữ liệu quyết định bằng nhau không thay đổi, các lần gọi hash trả về kết quả nhất quán.
- Nếu hai đối tượng bằng nhau theo `equals()` thì cả hai cũng có hash `1`.
- Nếu hai đối tượng **không** bằng nhau thì Java **không bắt buộc** mã băm khác nhau.

Do đó, mọi mục nhập đều có thể dùng hash cố định mà cấu trúc băm vẫn bảo toàn kết quả nghiệp vụ, miễn là các khóa còn tuân thủ hợp đồng, trạng thái dùng để so sánh vẫn ổn định khi được lưu, và cấu trúc được sử dụng đúng cách.

Tuy vậy, cách cài đặt này là **lựa chọn hiệu năng kém**. Một tập hợp lớn chứa hàng nghìn khóa khác nhau nhưng có cùng hash có thể phải kiểm tra nhiều ứng viên hơn so với trường hợp hash phân bố tốt. Một triển khai `HashMap` có thể dùng cấu trúc dữ liệu khác để giảm chi phí trong một số tình huống, nhưng không có lý do gì để cố ý tạo mọi collision trong ứng dụng thật.

Có thể nói:

> **Hàm băm tốt giúp hiệu quả; `equals()` đúng cùng hợp đồng `hashCode()` giúp đúng đắn.**

Câu này không có nghĩa hiệu năng luôn tách biệt hoàn toàn khỏi trải nghiệm thực tế: collision quá nhiều có thể khiến thao tác chậm đến mức gây timeout hoặc giảm khả năng phục vụ. Nhưng đó là hệ quả hiệu năng/khả dụng, khác với việc `HashMap` lặng lẽ gộp hai khóa không bằng nhau thành một.

## 5. So sánh tác động lên ba thao tác quan trọng

### 5.1. `put(key, value)`

Khi thêm mục nhập có khóa chưa bằng khóa hiện hữu, `HashMap` phải lưu thành mục nhập riêng ngay cả khi hash trùng. Khi thêm khóa **bằng** khóa hiện hữu, `put` cập nhật giá trị đang gắn với khóa đó.

Ví dụ `new Key(10)` và `new Key(20)` đều có hash 1 nhưng tồn tại song song. Trong khi `new Key(10)` lần thứ hai bằng khóa `Key(10)` cũ, vì vậy cập nhật mục nhập của cùng khóa logic.

### 5.2. `get(key)` và `containsKey(key)`

Hash giúp xác định vùng ứng viên. Trường hợp các khóa có hash trùng, thao tác phải tiếp tục dùng ngữ nghĩa bằng nhau để chọn kết quả đúng.

Nếu có `Key(10)` và `Key(20)`, truy vấn `Key(99)` cho `null` ở `get` và `false` ở `containsKey` mặc dù tất cả đều có hash 1.

**Lưu ý:** `map.get(key) == null` không luôn chứng minh khóa vắng mặt, vì `HashMap` cho phép một mục nhập có giá trị `null`. Khi cần phân biệt “không có khóa” và “có khóa với value là `null`”, dùng `containsKey(key)`.

### 5.3. `HashSet.add(element)` và `contains(element)`

Trong `HashSet`, nếu một phần tử **khác** theo `equals` thì được thêm dù hash trùng. Nếu phần tử bằng phần tử đã có, lời gọi `add` trả về `false`.

Điều kiện trùng lặp là **bằng nhau theo hợp đồng của phần tử**, không phải đơn thuần `hashCode()` bằng nhau. Đây là lý do ví dụ thêm `equivalentA` không tăng kích thước tập hợp, còn thêm `b` lại tăng.

## 6. Ranh giới giữa hiệu năng và tính đúng đắn

| Khía cạnh | Collision nhiều có thể gây ra | Collision tự nó không gây ra |
| --- | --- | --- |
| Lưu trữ khóa | Nhiều mục nhập phải cùng chia sẻ một vùng hoặc nhóm ứng viên | Không tự xóa khóa khác nhau theo `equals` |
| Tra cứu | Có thể tốn thêm công sức phân biệt ứng viên | Không tự làm `get` trả giá trị của một khóa không bằng khóa truy vấn |
| `HashSet` | Có thể tăng chi phí thêm và kiểm tra thành viên | Không tự loại bỏ phần tử khác nhau chỉ vì hash trùng |
| Tăng dữ liệu | Hiệu năng có thể suy giảm khi phân bố băm kém | Không thay đổi hợp đồng logic của `Map`/`Set` |

Về độ phức tạp, các thao tác trên bảng băm thường được kỳ vọng hiệu quả trung bình khi phân bố hash tốt. Trong trường hợp phân bố rất kém, việc xử lý nhiều ứng viên có thể tốn thời gian đáng kể. Đừng đưa ra một độ phức tạp cụ thể cho **mọi** triển khai và hoàn cảnh, vì Java có thể tối ưu việc xử lý bucket theo kích thước bảng, số lượng mục nhập và kiểu khóa.

Khi đánh giá ứng dụng thực tế, một hàm hash tốt phải có phân bố đủ phù hợp cho dữ liệu sử dụng, trả về kết quả ổn định theo hợp đồng và tương thích với `equals`. Không thể đánh giá tính đúng đắn của khóa chỉ bằng cách thống kê số collision; cần kiểm tra cả quy tắc `equals`.

## 7. Vấn đề nào thực sự có thể làm cấu trúc băm trả kết quả sai?

Collision hợp lệ khác với các lỗi sau.

### 7.1. Vi phạm chiều bắt buộc của hợp đồng `equals()/hashCode()`

Giả sử hai đối tượng được `equals` xem là bằng nhau nhưng `hashCode()` lại khác:

```text
a.equals(b) == true
a.hashCode() != b.hashCode()  // Vi phạm hợp đồng
```

Đây là lỗi thiết kế của lớp khóa. Khi bộ sưu tập dựa trên hash để khoanh vùng tra cứu, những khóa logic bằng nhau có mã băm không tương thích có thể không tìm thấy nhau hoặc xuất hiện trùng lặp không mong muốn.

Ví dụ về **phản mẫu** bên trong một lớp có trường `int id` và `String name`:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return id == other.id;
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(name); // Sai hợp đồng
}
```

Đây là **đoạn minh họa lỗi, không phải chương trình độc lập**. Hai đối tượng có cùng `id` nhưng `name` khác nhau được xem là bằng nhau, trong khi hash có thể khác. Cách sửa là tính hash nhất quán từ `id` nếu `id` thực sự là trường duy nhất quyết định bằng nhau.

Đừng cố “sửa collision” bằng cách cho mọi đối tượng một hash khác nhau bằng mọi giá; việc đó không giải quyết hợp đồng giữa `equals` và `hashCode`.

### 7.2. Thay đổi trường làm khóa sau khi chèn

Giả sử một khóa được thêm vào `HashMap` với hash tính từ `id = 10`. Sau đó chương trình sửa `id` thành `20`, khiến hash mới khác hash được dùng khi chèn. Việc tra cứu có thể đi đến nhóm ứng viên khác và không tìm được mục nhập.

Đây là **lỗi do khóa biến đổi trạng thái**, không phải collision. Đặc biệt với các trường tham gia `equals/hashCode`, nên dùng khóa bất biến hoặc có chiến lược loại bỏ rồi thêm lại khi cần thay đổi.

Các khóa `record Key(int id)` trong ví dụ không có setter, và thành phần kiểu nguyên thủy `id` là bất biến, nên tránh được trường hợp này.

### 7.3. `equals()` thiếu tính đối xứng, bắc cầu hoặc nhất quán

Nếu `a.equals(b)` và `b.equals(a)` cho kết quả khác nhau, hoặc quan hệ bằng nhau thay đổi bất thường khi dữ liệu liên quan không đổi, cấu trúc băm khó có thể hoạt động theo kỳ vọng. Vấn đề phát sinh từ hợp đồng của lớp khóa, không phải chỉ vì hai giá trị hash trùng nhau.

### 7.4. Sử dụng đồng thời không đúng cách

`HashMap` và `HashSet` thông thường không cung cấp an toàn luồng cho mọi thao tác ghi/đọc đồng thời. Nếu nhiều luồng thay đổi cấu trúc mà không đồng bộ hóa thích hợp, chương trình có thể gặp hành vi không mong muốn. Đây là vấn đề **truy cập đồng thời**, không phải tính sai của thuật toán xử lý collision.

Nếu cần cấu trúc dùng đồng thời, lựa chọn tương thích như `ConcurrentHashMap` và cơ chế đồng bộ phù hợp với yêu cầu ứng dụng; không nên đổ lỗi cho collision khi nguyên nhân là race condition.

## 8. Các lỗi tư duy thường gặp

1. **“Hai khóa cùng hash thì mục nhập thứ hai ghi đè mục nhập thứ nhất.”** Sai. `HashMap` cập nhật khi khóa bằng nhau theo ngữ nghĩa khóa; collision không đủ.
2. **“`HashSet` chỉ chứa tối đa một phần tử cho mỗi hash.”** Sai. Nhiều phần tử khác nhau theo `equals` có thể có cùng hash và cùng tồn tại.
3. **“Không có collision mới chứng minh code đúng.”** Sai. Không có collision trong dữ liệu thử nghiệm không bảo đảm `equals/hashCode` đúng hợp đồng.
4. **“Collision xảy ra nghĩa là mất dữ liệu.”** Sai. Cấu trúc băm đúng phải có cơ chế phân biệt các khóa va chạm.
5. **“Hash duy nhất là định danh đối tượng.”** Sai. Giá trị `int` không được bảo đảm duy nhất; `hashCode()` cũng không có nghĩa là địa chỉ bộ nhớ.
6. **“Chỉ cần `hashCode()` giống nhau là có thể bỏ gọi `equals()`.”** Sai. Nếu bạn tự xây cấu trúc băm, đây có thể là lỗi nghiêm trọng làm gộp hai khóa khác nhau.
7. **“Hash luôn bằng 1 là thực hành tốt vì vẫn chạy đúng.”** Sai. Nó có thể đúng hợp đồng nhưng làm phân bố tệ, ảnh hưởng đáng kể đến hiệu năng.
8. **“Thấy `get` sai thì chắc do collision.”** Trước tiên kiểm tra hợp đồng `equals/hashCode`, tính ổn định của khóa, chính sách `null`, logic thao tác và truy cập đồng thời.

## 9. Bài tập suy luận không cần chạy chương trình

Cho lớp `Key` từ ví dụ có `hashCode() == 1` cho mọi instance và `equals` so sánh `id`, xét lần lượt:

```java
Map<Key, String> map = new HashMap<>();

map.put(new Key(1), "A");
map.put(new Key(2), "B");
map.put(new Key(1), "A2");

int size = map.size();
String one = map.get(new Key(1));
String two = map.get(new Key(2));
String unknown = map.get(new Key(3));
boolean presentThree = map.containsKey(new Key(3));
```

Đây là đoạn mã cần đặt trong một phương thức có các import cần thiết và có thể truy cập `record Key` được định nghĩa trong chương trình ở phần 3.

**Đáp án:**

- `size == 2` vì `Key(1)` và `Key(2)` là hai khóa khác nhau, còn `Key(1)` được thêm lần thứ hai chỉ cập nhật giá trị.
- `one` là `"A2"` vì giá trị mới đã thay giá trị cũ của khóa tương đương `Key(1)`.
- `two` là `"B"` vì collision không ghi đè khóa `Key(2)`.
- `unknown == null` và `presentThree == false` vì `Key(3)` không bằng khóa nào đang lưu, mặc dù hash vẫn là `1`.

Hãy thay `Key` bằng một kiểu có hash phân bố tốt hơn nhưng giữ nguyên định nghĩa bằng nhau theo `id`. Nếu cài đặt vẫn tuân thủ hợp đồng và trạng thái khóa không đổi, các kết quả nghiệp vụ trên **phải giữ nguyên**; chỉ cách phân bố và hiệu năng có thể khác.

## 10. Khi nào cần hành động trong dự án thực tế?

Nếu quan sát nhiều collision hoặc thao tác `HashMap` chậm, hãy đánh giá phân bố mã băm theo **dữ liệu thật** và cách cài đặt `hashCode()`. Các trường hợp số lượng lớn khóa có chung hash có thể làm giảm hiệu năng; thử nghiệm với dữ liệu đặc trưng sẽ hữu ích hơn việc giả định hash luôn ngẫu nhiên.

Nếu lại quan sát thấy khóa “biến mất”, có nhiều khóa bằng nhau cùng xuất hiện, hoặc `HashSet.contains` trả về kết quả bất thường, nên kiểm tra theo thứ tự:

1. `equals()` có tuân thủ tính phản xạ, đối xứng, bắc cầu, nhất quán và xử lý `null` đúng không?
2. Hai đối tượng bằng nhau có luôn cho cùng hash không?
3. Các trường tham gia tính bằng nhau và hash có thay đổi sau khi chèn không?
4. Mã có truy cập đồng thời vào cấu trúc không an toàn luồng hoặc sử dụng sai một API liên quan không?
5. Có nhầm việc `Map.get` trả `null` với sự vắng mặt của khóa có giá trị `null` không?

Các bước này tập trung vào những nguyên nhân có thể làm sai hành vi. Collision hợp lệ chỉ là đặc tính cần được cấu trúc băm xử lý đúng và có thể cần tối ưu về hiệu năng khi tần suất quá lớn.

## Ghi nhớ

**Va chạm hash là việc nhiều khóa khác nhau cho cùng mã băm; nó không đồng nghĩa với việc các khóa bằng nhau hoặc dữ liệu bị mất.** `HashMap` và `HashSet` phân biệt khóa/phần tử bằng ngữ nghĩa bằng nhau, nên có thể giữ nhiều khóa cùng hash mà vẫn tra cứu và cập nhật chính xác. Collision quá nhiều có thể làm chậm thao tác; lỗi hợp đồng `equals/hashCode`, khóa bị thay đổi hoặc dùng cấu trúc sai mới là những nguồn rủi ro rõ ràng cho tính đúng đắn.