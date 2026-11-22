# Thay đổi trường sắp xếp khi đối tượng đang nằm trong cây `TreeSet` hoặc `TreeMap`

## 1. Điều gì xảy ra khi trường dùng để sắp xếp bị thay đổi?

`TreeSet<E>` và `TreeMap<K, V>` của Java duy trì dữ liệu trong cấu trúc cây tìm kiếm có cân bằng, được sắp xếp theo **thứ tự tự nhiên** (`Comparable.compareTo`) hoặc một **`Comparator`** được cung cấp. Khi thêm phần tử hoặc khóa, cây dùng kết quả so sánh để xác định vị trí và cân bằng cấu trúc.

Nếu bạn **thay đổi một trường tham gia `compareTo`/`Comparator` khi đối tượng vẫn còn trong cây**, thứ tự đúng theo giá trị mới có thể không còn khớp vị trí đã xác định từ trước. Cây **không tự phát hiện thay đổi bên trong đối tượng**, không tự rút nút ra rồi chèn lại, và không tự sắp xếp lại toàn bộ mỗi lần đối tượng đổi trạng thái.

Ví dụ, tại lúc chèn một cây có ba công việc:

```text
Các khóa theo thứ tự: A(10), B(20), C(30)
Trong đó số trong ngoặc là độ ưu tiên dùng để so sánh.

Đổi A.priority: 10 -> 25 khi A vẫn nằm trong cây.
Giá trị mới cần xếp: B(20), A(25), C(30).
Nhưng cây vẫn có thể duyệt theo vị trí cũ: A(25), B(20), C(30).
```

Khi đó, giả định mỗi nhánh trái chứa các khóa nhỏ hơn và nhánh phải chứa các khóa lớn hơn theo bộ so sánh hiện tại đã bị phá vỡ. **Không nên tiếp tục dựa vào kết quả tìm, thêm, xóa, duyệt hoặc truy vấn khoảng** của tập hợp đó như thể cấu trúc vẫn hợp lệ.

Đây là vấn đề **đột biến khóa sắp xếp khi đã lưu trong cây** (mutable ordering key), không phụ thuộc vào việc trường đó có được khai báo là `private` hay không. Setter, phản chiếu (reflection), thao tác qua tham chiếu khác, hoặc thay đổi trạng thái bên ngoài mà `Comparator` đọc đều có thể gây tình huống tương tự.

## 2. Vì sao `TreeSet`/`TreeMap` không sắp xếp lại tự động?

Trong cấu trúc có thứ tự, việc tìm kiếm dựa trên các so sánh nối tiếp từ một nút tới các nhánh cây. Thao tác như `TreeSet.contains(value)` hoặc `TreeMap.get(key)` không quét tất cả nút để kiểm tra lại mọi trường; chúng dựa vào **quan hệ thứ tự đã dùng để tổ chức cây**.

Khi một khóa từng nằm ở nhánh dành cho giá trị nhỏ bị sửa thành giá trị lớn, phép tìm với khóa mới có thể đi theo nhánh khác và **không gặp đúng đối tượng đã lưu**. Cũng có thể xuất hiện các hậu quả:

- `contains()` / `get()` trả kết quả bất ngờ (chẳng hạn báo không tìm thấy dù đối tượng còn trong tập hợp).
- `remove()` hoặc `TreeMap.remove()` không định vị được phần tử/khóa, vì thuật toán tìm theo giá trị đã thay đổi.
- Thứ tự duyệt không còn tăng dần theo `compareTo()`/`Comparator` hiện tại.
- Việc thêm giá trị mới có thể gặp xung đột với khóa cũ, để lại những phần tử mà phép so sánh hiện nay coi là tương đương hoặc khiến tập hợp có hành vi khó dự đoán.
- `first()`, `last()`, `floor()`, `ceiling()`, `headSet()`, `tailSet()`, `subSet()` và các thao tác khoảng trên `NavigableMap` có thể không còn phản ánh đúng thứ tự kỳ vọng.

Những triệu chứng cụ thể có thể thay đổi theo cấu trúc cây và đường đi thuật toán. Việc một lần gọi `contains()` tình cờ vẫn trả `true` **không chứng minh việc sửa khóa tại chỗ là an toàn**.

## 3. Điều kiện phải giữ ổn định

Trong thời gian một đối tượng được dùng làm **phần tử của `TreeSet`** hoặc **khóa của `TreeMap`**, các dữ liệu quyết định kết quả so sánh với phần tử/khóa khác phải ổn định.

Ví dụ nếu `compareTo()` so theo `priority` rồi `id`, cả `priority` lẫn `id` phải có ngữ nghĩa cố định đối với vị trí trong cây. Nếu `Comparator` so theo `user.getDepartment().getName()`, việc đổi tên phòng ban cũng có thể thay đổi kết quả so sánh **dù trường trực tiếp trên đối tượng `user` không đổi**.

Đây là lý do nên ưu tiên **khóa bất biến**: các trường dùng để so sánh là `final`, các thành phần lồng bên trong cũng không thể bị sửa theo cách ảnh hưởng thứ tự. `record` có thể hữu ích cho khóa giá trị bất biến nông; cần lưu ý rằng trường `final` trỏ tới một đối tượng mutable vẫn có thể khiến dữ liệu được comparator đọc thay đổi.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Chương trình sau cho thấy việc thay đổi trường sắp xếp tại chỗ làm thứ tự duyệt không còn tăng dần, và hai cách tạo lại thứ tự đúng. Lưu dưới tên **`MutableTreeKeyDemo.java`**:

```java
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;

public class MutableTreeKeyDemo {
    private static final class Job implements Comparable<Job> {
        private final String id;
        private int priority;

        Job(String id, int priority) {
            this.id = Objects.requireNonNull(id);
            this.priority = priority;
        }

        void setPriority(int priority) {
            this.priority = priority;
        }

        @Override
        public int compareTo(Job other) {
            int byPriority = Integer.compare(priority, other.priority);
            return byPriority != 0 ? byPriority : id.compareTo(other.id);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Job other)) return false;
            return priority == other.priority && id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, priority);
        }

        @Override
        public String toString() {
            return id + "(" + priority + ")";
        }
    }

    private static boolean isSorted(TreeSet<Job> set) {
        Job previous = null;
        for (Job current : set) {
            if (previous != null && previous.compareTo(current) > 0) {
                return false;
            }
            previous = current;
        }
        return true;
    }

    public static void main(String[] args) {
        Job a = new Job("A", 10);
        Job b = new Job("B", 20);
        Job c = new Job("C", 30);
        TreeSet<Job> broken = new TreeSet<>();
        broken.add(a);
        broken.add(b);
        broken.add(c);
        System.out.println("before mutation: " + broken);

        a.setPriority(25); // Sai: phần tử vẫn nằm trong cây
        System.out.println("after mutation: " + broken);
        System.out.println("order still valid: " + isSorted(broken));

        TreeSet<Job> rebuilt = new TreeSet<>();
        for (Job job : broken) {
            rebuilt.add(job);
        }
        System.out.println("rebuilt: " + rebuilt);
        System.out.println("rebuilt order valid: " + isSorted(rebuilt));

        Job safeA = new Job("A", 10);
        TreeSet<Job> safe = new TreeSet<>();
        safe.add(safeA);
        safe.add(new Job("B", 20));
        safe.add(new Job("C", 30));
        boolean removed = safe.remove(safeA); // Xóa bằng giá trị cũ
        safeA.setPriority(25);
        boolean inserted = safe.add(safeA);   // Chèn bằng giá trị mới
        System.out.println("safe remove: " + removed);
        System.out.println("safe reinsert: " + inserted);
        System.out.println("safe result: " + safe);

        Job mapKey = new Job("K", 5);
        TreeMap<Job, String> map = new TreeMap<>();
        map.put(mapKey, "pending");
        String oldValue = map.remove(mapKey); // Xóa trước khi sửa khóa
        mapKey.setPriority(7);
        map.put(mapKey, oldValue);
        map.replace(mapKey, "done");
        System.out.println("TreeMap value: " + map.get(mapKey));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac MutableTreeKeyDemo.java
java MutableTreeKeyDemo
```

Kết quả với chương trình này trên các triển khai Java thông dụng tuân theo hợp đồng collection:

```text
before mutation: [A(10), B(20), C(30)]
after mutation: [A(25), B(20), C(30)]
order still valid: false
rebuilt: [B(20), A(25), C(30)]
rebuilt order valid: true
safe remove: true
safe reinsert: true
safe result: [B(20), A(25), C(30)]
TreeMap value: done
```

Ở đây, `Job.compareTo` xét `priority` trước rồi `id` để hai công việc trùng ưu tiên nhưng khác mã vẫn được phân biệt. `equals()` và `hashCode()` được cài đặt phù hợp với hai trường đó; điều này **không làm phép đổi `priority` khi phần tử đang trong cây trở nên an toàn**.

Chương trình cố ý không dựa vào kết quả `broken.contains(a)` sau khi sửa trường, vì kết quả có thể tùy thuộc cách tổ chức cây. Việc thứ tự duyệt `[A(25), B(20), C(30)]` không tăng dần đã đủ minh họa vi phạm bất biến thứ tự; cây cũ không nên tiếp tục được sử dụng. Ví dụ tạo `rebuilt` bằng cách chèn **từng phần tử** theo so sánh hiện tại, không dựa vào việc sao chép nguyên trạng cây đã sai.

Trong phần `safe`, việc `remove(safeA)` diễn ra **trước** khi `safeA` thay đổi, nên phép xóa có thể tìm phần tử bằng các dữ liệu sắp xếp cũ. Chèn lại sau khi đổi giá trị giúp cấu trúc cây tổ chức vị trí mới. Nếu phép xóa thất bại, phải xử lý lỗi thay vì tiếp tục sửa và chèn như thể nó đã thành công.

## 5. Cách sửa an toàn trong ứng dụng

### Cách 1: Dùng đối tượng khóa bất biến, thay bằng đối tượng mới

Nếu muốn thay độ ưu tiên của phần tử, thiết kế một giá trị mới rồi cập nhật tập hợp:

```java
record JobKey(String id, int priority) { }

// Minh họa trong một phương thức:
// TreeSet<JobKey> sorted = new TreeSet<>(
//     Comparator.comparingInt(JobKey::priority).thenComparing(JobKey::id));
// JobKey oldKey = new JobKey("A", 10);
// sorted.add(oldKey);
// sorted.remove(oldKey);
// sorted.add(new JobKey("A", 25));
```

`JobKey` là một `record` và phần chú thích bên dưới mô tả **các dòng đặt trong phương thức**; muốn chạy đầy đủ, khai báo comparator, import `TreeSet`/`Comparator` và đặt mã trong lớp/phương thức thích hợp. Ý chính là không thay đổi trường dùng để xếp thứ tự trên đối tượng đang được lưu. Với `record` chỉ chứa `String` và `int` như trên, cả hai thành phần đều bất biến.

### Cách 2: `remove` trước, mutate sau, rồi `add` lại

Nếu bắt buộc phải dùng đối tượng có thể thay đổi:

```text
1. Tìm phần tử/khóa với trạng thái cũ.
2. Loại bỏ khỏi cây bằng trạng thái cũ.
3. Chỉ sau khi xóa thành công, thay đổi các trường so sánh.
4. Thêm trở lại với trạng thái mới.
5. Kiểm tra kết quả thêm/cập nhật và xử lý xung đột compareTo == 0.
```

Đây là trình tự áp dụng được với `TreeSet`; đối với `TreeMap`, cần lưu lại **giá trị gắn với khóa** trước khi xóa, rồi `put` khóa đã thay đổi cùng giá trị cần thiết. Đừng đánh đồng `TreeMap.remove(k)` trả `null` với việc chắc chắn không có khóa nếu map cho phép giá trị `null`: dùng `containsKey(k)` trước khi xóa hoặc quản lý trạng thái theo nghiệp vụ.

**Quan trọng:** Không sửa khóa **trước** rồi mới `remove`; lúc đó thuật toán xóa cũng có thể không tìm thấy nó. Nếu lỡ sửa rồi, hãy xây dựng một cây mới từ dữ liệu nguồn tin cậy, kiểm tra xung đột theo comparator và thay thế cây cũ có kiểm soát.

### Cách 3: Xây lại toàn bộ cây khi cần cập nhật hàng loạt

Khi nhiều khóa cần đổi theo đợt, có thể thu thập các phần tử, hoàn tất cập nhật **bên ngoài tập hợp đang được sử dụng**, rồi chèn từng phần tử vào một `TreeSet`/`TreeMap` mới với comparator ổn định. Điều này bảo đảm việc xác định vị trí dựa trên giá trị mới.

Ví dụ `new TreeSet<>(someSortedSet)` không nên được xem là một biện pháp sửa lỗi chắc chắn nếu nguồn **đã vi phạm thứ tự**: một số đường triển khai có thể tận dụng tính “đã sắp xếp” của nguồn. Thay vào đó, khởi tạo cây trống và `add`/`put` từng phần tử như ví dụ `rebuilt`.

Đối với `TreeMap`, khi xây lại phải xác định chính sách nếu **nhiều khóa sau thay đổi cùng so sánh bằng `0`**, vì `put` có thể ghi đè giá trị của khóa tương đương; việc mất một ánh xạ có thể gây lỗi nghiệp vụ.

## 6. Cần phân biệt thay đổi khóa và thay đổi giá trị

| Thay đổi | Ảnh hưởng tới thứ tự cây |
| --- | --- |
| Đổi `priority` của phần tử `TreeSet` khi comparator xét `priority` | **Không an toàn**, cây không tự cập nhật vị trí |
| Đổi trường của khóa `TreeMap` mà `compareTo`/`Comparator` sử dụng | **Không an toàn**, tra cứu có thể sai |
| Đổi một trường trên phần tử mà comparator **hoàn toàn không đọc** | Không làm hỏng thứ tự vì riêng thay đổi đó, miễn quan hệ so sánh thực sự vẫn ổn định |
| Gọi `map.put(existingKey, newValue)` hoặc `map.replace(existingKey, newValue)` với khóa ổn định | **An toàn cho thứ tự cây** vì chỉ cập nhật giá trị |
| Thay đổi nội dung đối tượng làm **value** trong `TreeMap` và comparator chỉ xét khóa | Không tự làm hỏng thứ tự các khóa |
| Đổi trạng thái bên ngoài mà comparator sử dụng (cấu hình, bảng ưu tiên, thuộc tính lồng nhau) | Có thể **không an toàn** dù đối tượng khóa không thay trực tiếp |

Lưu ý: một đối tượng có `equals()` và `hashCode()` phụ thuộc vào trường mutable còn có thể gặp vấn đề tương tự trong `HashSet`/`HashMap`, nhưng ở đó nguyên nhân chính là **bucket băm** theo hash cũ. Với cây có thứ tự, nguyên nhân chính là **quan hệ so sánh và vị trí nút**.

## 7. `compareTo() == 0` và xung đột khi chèn lại

`TreeSet` và `TreeMap` dùng `compareTo()`/`Comparator.compare()` để xác định hai khóa **tương đương theo thứ tự**, tức kết quả so sánh bằng `0`. Sau khi đổi một trường, phần tử cũ có thể trở nên tương đương với một phần tử khác đã có trong cây.

Ví dụ hai công việc có cùng `priority` nếu comparator **chỉ so sánh `priority`** thì có thể bị coi là một khóa, ngay cả khi `id` khác nhau. `TreeSet.add()` khi đó trả `false`, còn `TreeMap.put()` có thể cập nhật giá trị của khóa đã có.

Vì vậy, xác định từ trước liệu cùng độ ưu tiên có được phép chứa nhiều công việc không. Nếu có, comparator cần một tiêu chí phụ ổn định, ví dụ:

```java
Comparator<Job> order = Comparator
        .comparingInt((Job job) -> job.priority)
        .thenComparing(job -> job.id);
```

Đây là **đoạn đặt trong ngữ cảnh có lớp `Job` và `import java.util.Comparator`**; nếu `Job` là lớp như ví dụ phía trên và mã nằm ngoài lớp lồng, quyền truy cập trường private cần được xử lý phù hợp. Dù có tiêu chí phụ, `priority` vẫn là trường tham gia so sánh và **vẫn không được sửa khi phần tử đang nằm trong cây**.

Bên cạnh đó, hợp đồng `Comparable`/`Comparator` yêu cầu tính phản đối xứng về dấu, tính bắc cầu và sự nhất quán khi hai giá trị so sánh bằng `0` với mọi giá trị thứ ba. Bộ so sánh sai hợp đồng có thể làm cây không ổn định **ngay cả khi trường không thay đổi**.

## 8. Checklist kỹ thuật khi cập nhật một khóa có thứ tự

- Xác nhận dữ liệu nào thực sự tham gia `compareTo`/`Comparator`, kể cả thuộc tính lồng nhau hay trạng thái bên ngoài.
- Ưu tiên tạo một **khóa bất biến mới** và thay thế bằng thao tác xóa/chèn.
- Nếu cần dùng cùng đối tượng mutable, luôn kiểm tra `remove` thành công **trước** khi thay đổi trường so sánh.
- Với `TreeMap`, giữ nguyên giá trị cần thiết khi xóa rồi chèn khóa đã cập nhật; phân biệt key absence với null value.
- Kiểm tra xem khóa mới có bị `compareTo == 0` với khóa khác hay không và xử lý đúng chính sách nghiệp vụ.
- Khi cây đã hỏng vì thay đổi tại chỗ, xây lại từ dữ liệu chuẩn bằng cách **chèn lại từng khóa**; đừng dựa vào truy vấn cây cũ để chứng minh tính đúng.
- Trong chương trình đa luồng, đồng bộ hóa/điều phối thao tác cập nhật và truy cập phù hợp; `TreeSet`/`TreeMap` thường không tự đồng bộ các thay đổi song song.

## 9. Câu hỏi tự kiểm tra

1. Đã chèn `Task(priority=10)` vào `TreeSet`, sau đó đổi `priority` thành `50` bằng setter. Cây có tự chuyển nút sang vị trí đúng không? **Không**; cần xóa trước rồi chèn lại hoặc xây tập hợp mới.
2. Đã đổi trường khóa rồi mới gọi `remove(key)`. Có bảo đảm xóa được không? **Không**; đường tìm kiếm có thể không còn đi đến nút đã lưu.
3. Thay đổi `value` trong `TreeMap` có làm hỏng thứ tự khóa không? **Không**, nếu bộ so sánh chỉ phụ thuộc khóa và khóa vẫn ổn định.
4. Nếu comparator chỉ xét `priority`, sau khi sửa hai công việc có cùng ưu tiên rồi chèn lại thì sao? **Có thể trùng khóa theo `compare == 0`**; cần xử lý hoặc thêm tiêu chí phụ.
5. Sao chép trực tiếp từ một `SortedSet` đã sai thứ tự có luôn sửa được không? **Không**; nên tạo tập hợp trống và chèn từng phần tử với comparator hiện tại.

**Ghi nhớ:** `TreeSet`/`TreeMap` xây cấu trúc dựa trên kết quả so sánh **tại thời điểm thao tác với khóa**. Thay đổi dữ liệu quyết định thứ tự khi đối tượng còn nằm trong cây làm mất bất biến của cây. Hãy dùng khóa bất biến, hoặc **remove → thay đổi → add/put** theo đúng thứ tự; nếu cấu trúc đã không hợp lệ, xây lại từ dữ liệu đáng tin cậy.