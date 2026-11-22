# Tập hợp không sửa được và phần tử vẫn có thể thay đổi

## 1. Hai khái niệm cần tách biệt

Trong Java, một collection có thể không cho phép thêm, xóa hoặc thay thế phần tử, nhưng các đối tượng đang được collection tham chiếu vẫn có thể thay đổi trạng thái bên trong.

Ví dụ, một `List<Profile>` không cho phép gọi `add` hoặc `remove`, nhưng nếu `Profile` có phương thức `rename`, mã gọi vẫn có thể đổi tên một phần tử thông qua tham chiếu lấy từ list. Collection bảo vệ cấu trúc chứa phần tử; nó không tự động đóng băng các đối tượng phần tử.

Đây là khác biệt giữa:

- **Không sửa được cấu trúc (unmodifiable collection):** không thể thay đổi quan hệ thành viên hoặc thứ tự phần tử thông qua API của collection đó.
- **Bất biến sâu (deep immutability):** cả cấu trúc collection và trạng thái có thể quan sát của các đối tượng bên trong đều không thể thay đổi.

Nhiều API collection trong Java cung cấp tính không sửa được ở mức cấu trúc. Chúng không mặc nhiên tạo ra một đồ thị đối tượng bất biến sâu.

## 2. Ví dụ: list không sửa được nhưng phần tử vẫn thay đổi

Ví dụ sau tạo một list bằng `List.of`. List không cho phép thêm phần tử, nhưng nó vẫn giữ tham chiếu đến đối tượng `Profile`. Khi đối tượng được đổi tên, đọc lại phần tử từ list sẽ thấy tên mới.

```java
import java.util.List;

public class ShallowUnmodifiableDemo {
    static final class Profile {
        private String name;

        Profile(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String newName) {
            this.name = newName;
        }
    }

    public static void main(String[] args) {
        Profile alice = new Profile("Alice");
        List<Profile> members = List.of(alice);

        alice.rename("Alicia");
        System.out.println(members.get(0).name());

        try {
            members.add(new Profile("Bao"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("List structure is unmodifiable.");
        }
    }
}
```

Lưu mã nguồn trong tệp `ShallowUnmodifiableDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all ShallowUnmodifiableDemo.java
java ShallowUnmodifiableDemo
```

Kết quả:

```text
Alicia
List structure is unmodifiable.
```

Dòng đầu cho thấy phần tử đã đổi trạng thái dù list không cho phép thay đổi thành viên. Dòng thứ hai cho thấy thao tác thêm phần tử qua list không sửa được ném `UnsupportedOperationException`.

`List.of` được bổ sung từ Java 9. Nó tạo list không sửa được và từ chối phần tử `null`. Tính không sửa được của list không đồng nghĩa với việc các đối tượng mà list chứa cũng bất biến.

## 3. Unmodifiable view và snapshot là hai cách khác nhau

Java cung cấp các cách tạo collection không sửa được với hành vi khác nhau đối với collection nguồn.

### Collections.unmodifiableList: một view không sửa được

`Collections.unmodifiableList(source)` trả về một wrapper không cho phép thay đổi list thông qua wrapper đó. Wrapper vẫn nhìn vào list nguồn; nếu một tham chiếu khác sửa list nguồn, thay đổi đó được phản ánh khi đọc qua view.

```java
List<String> source = new ArrayList<>();
source.add("Java");

List<String> view = Collections.unmodifiableList(source);

source.add("Collections");

System.out.println(view); // [Java, Collections]
```

View không phải bản sao. Nó bảo vệ đường truy cập qua wrapper, nhưng không kiểm soát các tham chiếu khác đang giữ list nguồn.

### List.copyOf: snapshot không sửa được của các phần tử

Từ Java 10, `List.copyOf(source)` tạo một list không sửa được chứa các phần tử của collection nguồn tại thời điểm gọi. Thay đổi thành viên của list nguồn sau đó không được phản ánh trong kết quả.

```java
List<String> source = new ArrayList<>();
source.add("Java");

List<String> snapshot = List.copyOf(source);
source.add("Collections");

System.out.println(snapshot); // [Java]
```

`List.copyOf` từ chối collection nguồn có phần tử `null`. API bảo đảm kết quả không sửa được; không nên dựa vào việc nó luôn tạo một object list mới vì implementation có thể tái sử dụng một collection không sửa được phù hợp.

### Tạo snapshot không sửa được trên Java 9

Nếu cần giữ tương thích Java 9, có thể sao chép cấu trúc nguồn trước rồi bọc bản sao:

```java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(source)
);
```

Cách này tạo bản sao nông của các tham chiếu phần tử. Nó tách cấu trúc list mới khỏi list nguồn, nhưng không sao chép sâu từng phần tử.

## 4. Snapshot của collection vẫn là bản sao nông

`List.copyOf` và `new ArrayList<>(source)` sao chép các tham chiếu phần tử, không tự nhân bản đối tượng được tham chiếu. Do đó, nếu một phần tử là mutable object, thay đổi object đó vẫn được nhìn thấy từ snapshot.

Ví dụ:

```java
Profile profile = new Profile("Chi");

List<Profile> source = new ArrayList<>();
source.add(profile);

List<Profile> snapshot = List.copyOf(source);

source.add(new Profile("Dung"));
profile.rename("Chau");

System.out.println(snapshot.size());          // 1
System.out.println(snapshot.get(0).name());   // Chau
```

Kết quả thể hiện hai điều:

- Snapshot giữ số lượng và thứ tự tham chiếu có tại lúc tạo, nên phần tử mới thêm vào `source` không xuất hiện trong `snapshot`.
- Snapshot vẫn giữ cùng tham chiếu đến `profile`, nên thay đổi trạng thái của object đó được nhìn thấy khi truy cập qua snapshot.

Đây là *shallow copy* (bản sao nông). Muốn có bất biến sâu, cần thiết kế các phần tử cũng bất biến hoặc tạo bản sao phù hợp cho từng phần tử và các object lồng bên trong.

## 5. Áp dụng cho List, Set và Map

Nguyên tắc này áp dụng cho nhiều loại collection:

- Với `List<E>`, cấu trúc không sửa được vẫn có thể chứa các object `E` mutable.
- Với `Set<E>`, object phần tử vẫn có thể đổi trạng thái. Đặc biệt, tránh thay đổi các trường tham gia vào `equals` hoặc `hashCode` sau khi object được thêm vào hash-based set.
- Với `Map<K, V>`, map không sửa được vẫn có thể chứa value mutable. Tránh thay đổi trạng thái ảnh hưởng đến `equals` hoặc `hashCode` của key khi key đang được dùng trong hash-based map.

Nếu `hashCode` của một key hoặc set element thay đổi sau khi chèn, collection có thể không tìm thấy object bằng thao tác tra cứu hoặc xóa thông thường vì vị trí bucket được xác định dựa trên hash tại thời điểm chèn.

Các factory method hiện hành như `List.of`, `Set.of`, `Map.of` (Java 9) và `List.copyOf`, `Set.copyOf`, `Map.copyOf` (Java 10 trở lên) tạo collection không sửa được. Chúng không biến các object phần tử hoặc value thành bất biến sâu.

## 6. Cách thiết kế khi cần dữ liệu ổn định

Chọn cách bảo vệ theo yêu cầu thực tế:

1. **Chỉ cần ngăn người nhận sửa cấu trúc:** trả về unmodifiable view nếu muốn các thay đổi từ bên sở hữu nguồn tiếp tục hiển thị.
2. **Cần cố định thành viên tại thời điểm công bố:** tạo snapshot bằng `List.copyOf` trên Java 10+ hoặc sao chép rồi bọc bằng `Collections.unmodifiableList` trên Java 9.
3. **Cần phần tử không đổi:** dùng kiểu phần tử bất biến, chỉ cung cấp phương thức đọc, và tránh để lộ trạng thái mutable qua getter.
4. **Cần bất biến sâu cho collection lồng nhau:** sao chép hoặc chuyển đổi từng collection lồng nhau một cách đệ quy; chỉ bọc collection ngoài cùng là chưa đủ.
5. **Cần bảo vệ dữ liệu nhạy cảm hoặc trạng thái nội bộ:** không trả trực tiếp mảng, list hoặc object mutable nội bộ; trả về bản sao hoặc kiểu giá trị bất biến phù hợp.

Một `record` có các component khai báo bằng `final`, nhưng nếu component là một `List` mutable thì record vẫn có thể quan sát thấy nội dung list thay đổi. Muốn record có tính bất biến sâu ở mức mong muốn, constructor cần tạo bản sao không sửa được và các phần tử cũng phải đáp ứng yêu cầu bất biến.

Collection không sửa được cũng không tự bảo đảm an toàn luồng. Nếu collection nguồn của một unmodifiable view bị thay đổi đồng thời, ứng dụng vẫn cần cơ chế đồng bộ phù hợp. Wrapper chỉ giới hạn các thao tác thay đổi thông qua chính wrapper.

## 7. Checklist khi review

- Collection được tạo bằng factory không sửa được, snapshot hay unmodifiable view?
- Có tham chiếu nào khác có thể thay đổi collection nguồn không?
- Các phần tử bên trong có mutable field hoặc phương thức thay đổi trạng thái không?
- Collection lồng nhau có được sao chép/bảo vệ riêng không?
- Key trong `HashMap` hoặc phần tử trong `HashSet` có thể đổi `equals`/`hashCode` sau khi chèn không?
- API có cần snapshot thành viên, bất biến sâu hay chỉ cần chặn thao tác sửa qua một đường truy cập?
- Nếu chia sẻ giữa nhiều luồng, việc đồng bộ truy cập vào nguồn dữ liệu đã được thiết kế chưa?

Hãy xác định rõ phạm vi của từ “không sửa được”. Collection có thể bảo vệ cấu trúc của nó trong khi các object bên trong vẫn thay đổi. Muốn dữ liệu ổn định sâu, phải thiết kế cả collection, phần tử và các tham chiếu mà ứng dụng cho phép truy cập.