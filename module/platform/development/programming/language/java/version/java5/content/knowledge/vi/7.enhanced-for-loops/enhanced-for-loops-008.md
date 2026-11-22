# Phân biệt sửa đối tượng phần tử với thay phần tử trong collection

## 1. Ba thao tác trông giống nhau nhưng tác động khác nhau

Khi duyệt một collection bằng `for-each`, biến vòng lặp nhận giá trị của phần tử ở lượt hiện tại. Nếu phần tử là một đối tượng, giá trị ấy là một **tham chiếu tới đối tượng**, không phải bản sao toàn bộ đối tượng.

Vì vậy cần phân biệt ba việc:

| Thao tác | Thứ được thay đổi | Collection có giữ đối tượng khác ở vị trí đó không? |
| --- | --- | --- |
| `player.addPoints(5)` | Trạng thái của đối tượng mà `player` đang tham chiếu | Không; vẫn là đối tượng cũ, có trạng thái mới |
| `player = new Player(...)` | Giá trị của biến vòng lặp cục bộ | Không; phép gán không cập nhật phần tử trong collection |
| `players.set(index, new Player(...))` | Tham chiếu được lưu ở một vị trí trong `List` | Có, nếu thao tác được hỗ trợ và thành công |

`Player(...)` trong bảng chỉ biểu thị lời gọi hàm tạo; ví dụ chạy đầy đủ với các đối số cụ thể nằm ở mục 5.

Điểm mấu chốt là biến vòng lặp không phải một tên thay thế trực tiếp cho “ô chứa phần tử” trong collection. Đổi giá trị biến ấy không tự ghi trở lại vị trí mà phần tử đã được lấy ra.

Các quy tắc này vẫn áp dụng trong Java hiện hành. Ví dụ trong bài dùng JDK 17 trở lên.

## 2. Sửa đối tượng qua tham chiếu được lấy ra

Giả sử một `Player` có trường điểm số có thể thay đổi và phương thức `addPoints(int delta)`:

```java
for (Player player : players) {
    player.addPoints(5);
}
```

Trong một lượt, phần tử của danh sách và biến `player` cùng dẫn tới một đối tượng. Gọi `addPoints` làm thay đổi trường của chính đối tượng ấy. Sau vòng lặp, đọc lại đối tượng qua danh sách sẽ thấy điểm mới.

Không có thao tác sao chép `Player` trong vòng lặp trên. Nếu một biến khác cũng tham chiếu tới cùng `Player`, biến ấy cũng quan sát được trạng thái đã đổi.

Để nhìn cơ chế, với một `List<Player>`, có thể hiểu cách duyệt `for-each` theo dạng tương đương về ý nghĩa sau:

```java
for (Iterator<Player> iterator = players.iterator(); iterator.hasNext();) {
    Player player = iterator.next();
    player.addPoints(5);
}
```

Đoạn này cần `import java.util.Iterator;`; `Player` và `players` là các thành phần của ví dụ. Mỗi lượt gọi `next()` lấy một giá trị phần tử rồi gán vào biến cục bộ. Giá trị tham chiếu được sao chép, còn đối tượng mà nó trỏ tới không được sao chép.

Quy tắc của vòng `for-each` trên `Iterable` được mô tả tại [JLS §14.14.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2). Với mảng, cơ chế lấy phần tử khác nhưng việc gán lại biến vòng lặp cũng không tự ghi trở lại phần tử mảng.

## 3. Gán lại biến vòng lặp không thay phần tử

```java
for (Player player : players) {
    player = new Player("Temp", 0);
}
```

Đoạn mã tạo đối tượng mới và làm biến `player` trỏ tới đối tượng đó trong lượt hiện tại. Danh sách vẫn giữ tham chiếu cũ. Ở lượt tiếp theo, biến vòng lặp nhận phần tử tiếp theo từ nguồn duyệt.

Nếu muốn phần tử trong danh sách trở thành đối tượng mới, phải gọi một thao tác cập nhật của danh sách hoặc của một cơ chế sửa đổi phù hợp. Không có bước ghi ngược tự động sau khi kết thúc thân vòng lặp.

Tương tự, viết `player = null` không xóa phần tử khỏi danh sách và cũng không làm phần tử tại vị trí đó thành `null`. Nó chỉ đổi giá trị của biến cục bộ.

### Trường hợp Integer và String

```java
for (Integer count : counts) {
    count = count + 10;
}
```

`Integer` là đối tượng bất biến. Phép cộng sử dụng giá trị số, rồi kết quả được đóng hộp để gán vào biến cục bộ `count`; nó không sửa trạng thái của đối tượng `Integer` đã nằm trong danh sách và cũng không thay phần tử của danh sách.

Với `String`, những lời gọi tạo kết quả như `toUpperCase` cũng không sửa chuỗi gốc. Nếu gán kết quả vào biến vòng lặp, phần tử danh sách vẫn giữ nguyên trừ khi gọi một thao tác cập nhật collection riêng.

Đừng suy ra rằng “kiểu đối tượng thì sửa được, kiểu nguyên thủy thì không”. Cần phân biệt đối tượng có cho thay đổi trạng thái hay không, và câu lệnh đang đổi trạng thái đối tượng hay chỉ gán lại một biến.

## 4. Muốn thay phần tử phải dùng API thay phần tử

Với `List`, một cách rõ ràng là duyệt theo chỉ số và dùng `set`:

```java
for (int i = 0; i < players.size(); i++) {
    Player old = players.get(i);
    players.set(i, new Player(old.name(), old.points() + 100));
}
```

`set(i, value)` ghi một tham chiếu khác vào vị trí `i`. Nó không sửa đối tượng cũ; nếu còn một biến giữ tham chiếu cũ, đối tượng cũ vẫn tồn tại và vẫn có trạng thái cũ.

Cách duyệt theo chỉ số trong ví dụ phù hợp với `ArrayList`. Với những loại danh sách mà truy cập theo chỉ số tốn kém hơn, có thể dùng `ListIterator` để duyệt và thay phần tử vừa trả về:

```java
ListIterator<Player> iterator = players.listIterator();
while (iterator.hasNext()) {
    Player old = iterator.next();
    iterator.set(new Player(old.name(), old.points() + 100));
}
```

Đoạn này cần `import java.util.ListIterator;`. `iterator.set(...)` thay phần tử vừa được trả về bởi thao tác duyệt thích hợp, nếu danh sách và iterator hỗ trợ thao tác. Không dùng phép gán vào biến `old` để thay cho lời gọi `set`.

Với một danh sách hỗ trợ, `replaceAll` cũng cho phép cung cấp hàm tạo giá trị thay thế cho từng phần tử. Lựa chọn API nên làm rõ mục tiêu “thay phần tử”, thay vì giấu mục tiêu đó trong một vòng `for-each` chỉ gán lại biến.

Xem hợp đồng của [List.set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#set(int,E)) và [ListIterator.set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html#set(E)).

Không phải mọi collection đều có chỉ số và `set`. Một `Set` không có “vị trí i” để thay theo cách này; muốn cập nhật cấu trúc ấy cần xét hợp đồng loại collection và quy tắc nhận diện phần tử.

## 5. Chương trình chạy đầy đủ

Lưu thành `ElementMutationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ElementMutationDemo {
    static final class Player {
        private final String name;
        private int points;

        Player(String name, int points) {
            this.name = name;
            this.points = points;
        }

        String name() {
            return name;
        }

        int points() {
            return points;
        }

        void addPoints(int delta) {
            points += delta;
        }

        @Override
        public String toString() {
            return name + ":" + points;
        }
    }

    public static void main(String[] args) {
        List<Player> players = new ArrayList<>(
                List.of(new Player("An", 10), new Player("Binh", 20)));

        for (Player player : players) {
            player.addPoints(5);
        }
        System.out.println("after object mutation=" + players);

        for (Player player : players) {
            player = new Player("Temp", 0);
        }
        System.out.println("after local assignment=" + players);

        List<Integer> counts = new ArrayList<>(List.of(1, 2));
        for (Integer count : counts) {
            count = count + 10;
        }
        System.out.println("counts=" + counts);

        Player oldFirst = players.get(0);
        for (int i = 0; i < players.size(); i++) {
            Player old = players.get(i);
            players.set(i, new Player(old.name(), old.points() + 100));
        }
        System.out.println("after element replacement=" + players);
        System.out.println("old alias=" + oldFirst);
        System.out.println("same first object=" + (oldFirst == players.get(0)));

        List<Player> fixed = List.of(new Player("Chi", 30));
        for (Player player : fixed) {
            player.addPoints(5);
        }
        System.out.println("unmodifiable list, mutable element=" + fixed);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ElementMutationDemo.java
java ElementMutationDemo
```

Stdout:

```text
after object mutation=[An:15, Binh:25]
after local assignment=[An:15, Binh:25]
counts=[1, 2]
after element replacement=[An:115, Binh:125]
old alias=An:15
same first object=false
unmodifiable list, mutable element=[Chi:35]
```

Kết quả đầu cho thấy sửa trạng thái được quan sát qua danh sách. Kết quả thứ hai và thứ ba cho thấy gán lại biến vòng lặp không thay các phần tử. Sau `set`, danh sách giữ những đối tượng `Player` mới, còn `oldFirst` vẫn tham chiếu tới đối tượng cũ có 15 điểm.

Dòng cuối đặc biệt quan trọng: `List.of` không cho thay đổi các phần tử được lưu trong danh sách bằng thao tác sửa đổi danh sách, nhưng không làm đối tượng `Player` bên trong trở thành bất biến. Gọi `addPoints` vẫn đổi được trạng thái của `Player` đó.

## 6. Các ranh giới dễ nhầm

### 6.1. Danh sách không cho sửa không đồng nghĩa phần tử bất biến

Với `List.of(new Player("Chi", 30))`, lệnh `list.set(0, anotherPlayer)` bị từ chối lúc chạy bằng `UnsupportedOperationException`. Nhưng `list.get(0).addPoints(5)` tác động tới đối tượng phần tử, không gọi một thao tác thay phần tử của danh sách.

Nếu yêu cầu dữ liệu không thể bị thay đổi sâu bên trong, cần thiết kế phần tử bất biến hoặc một chiến lược sao chép phù hợp. Chỉ chọn một collection không cho sửa chưa tạo ra tính bất biến sâu cho các đối tượng được chứa.

`final` cũng cần đọc đúng cấp: một biến tham chiếu `final` không được gán lại, nhưng đối tượng mà nó tham chiếu vẫn có thể có trạng thái sửa đổi được. Có thể dùng `for (final Player player : players)` rồi gọi `player.addPoints(5)`; chỉ phép gán `player = ...` bị cấm.

### 6.2. Thay phần tử khác với thêm hoặc xóa khi đang duyệt

Sửa trường của một `Player` không tự thêm hay xóa phần tử trong `ArrayList`. Thay qua `List.set` cũng khác với thao tác thay đổi kích thước như `add` hoặc `remove`.

Không nên mở rộng ví dụ thành việc gọi `players.add(...)` hoặc `players.remove(...)` trực tiếp bên trong `for-each` rồi cho rằng đó cũng chỉ là “sửa một đối tượng”. Với những collection/iterator có cơ chế phát hiện thay đổi không phù hợp, có thể gặp `ConcurrentModificationException`; không dựa vào việc một lần thử chưa ném ngoại lệ để kết luận cách sửa đó hợp lệ.

Khi cần thêm/xóa trong quá trình duyệt, chọn API và cách duyệt hỗ trợ rõ thao tác ấy. Mục tiêu của bài này là nhận diện đúng thứ đang được sửa trước khi chọn công cụ.

### 6.3. Nhiều vị trí có thể cùng tham chiếu tới một đối tượng

Nếu một `Player` xuất hiện dưới cùng một tham chiếu ở hai vị trí của danh sách, vòng `for-each` có thể gọi `addPoints` lên chính đối tượng đó hai lần. Vòng lặp đi qua các phần tử/vị trí được nguồn cung cấp, không tự loại những đối tượng trùng tham chiếu.

Tương tự, sửa đối tượng qua một collection có thể được thấy từ collection khác nếu cả hai cùng chứa tham chiếu tới nó. Đây là chia sẻ đối tượng, không phải việc mọi collection tự đồng bộ nội dung phần tử với nhau.

### 6.4. Không coi mọi phép sửa đối tượng trong collection là an toàn

Ví dụ `Player` ở đây nằm trong `ArrayList` và chỉ thay đổi điểm. Với một đối tượng đang làm phần tử của `Set`, thay đổi các trường ảnh hưởng tới `equals`/`hashCode` có thể phá vỡ những giả định mà collection cần để tìm và nhận diện phần tử. Với cấu trúc sắp thứ tự, cũng cần giữ đúng quy tắc thứ tự.

Vì vậy “sửa đối tượng không thay tham chiếu phần tử” là mô tả cơ chế, không phải sự bảo đảm rằng mọi thay đổi trạng thái đều phù hợp với mọi loại collection. Tài liệu [Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html) nêu rõ giới hạn khi phần tử sửa đổi làm thay đổi quan hệ so sánh bằng trong lúc nó đang thuộc tập hợp.

## 7. Chọn đúng cách theo mục tiêu

| Mục tiêu | Cách thường phù hợp |
| --- | --- |
| Cập nhật trạng thái của chính đối tượng đang có | Gọi phương thức thay đổi trạng thái qua biến `for-each`, nếu hợp đồng đối tượng/collection cho phép |
| Tạo một đối tượng mới và đưa vào vị trí cũ trong List | `List.set`, `ListIterator.set` hoặc `replaceAll` được hỗ trợ |
| Chỉ tạo một biến tham chiếu khác để xử lý cục bộ | Gán vào biến cục bộ; không kỳ vọng cập nhật collection |
| Chuyển danh sách đối tượng bất biến thành giá trị mới | Tạo kết quả mới rồi thay phần tử hoặc tạo một danh sách kết quả riêng |
| Ngăn cả sửa cấu trúc lẫn sửa trạng thái phần tử | Thiết kế hợp đồng collection và tính bất biến của phần tử ở hai cấp riêng |

Trước khi viết vòng lặp, hãy xác định muốn giữ cùng đối tượng với trạng thái mới hay muốn collection giữ một đối tượng khác. Hai mục tiêu có tác động khác nhau tới các tham chiếu đang được chia sẻ.

## 8. Tự kiểm tra

1. Vì sao `player.addPoints(5)` có thể được thấy khi đọc lại qua danh sách?
2. `player = new Player("Temp", 0)` trong `for-each` có thay phần tử hiện tại không?
3. Vì sao `count = count + 10` với `Integer` không làm danh sách số thay đổi?
4. Sau khi `players.set(0, replacement)`, một biến còn giữ đối tượng cũ có tự trỏ tới `replacement` không?
5. `List.of` chứa đối tượng có thể sửa có làm mọi trạng thái bên trong bất biến không?

Đáp án:

1. Vì biến vòng lặp và phần tử danh sách dẫn tới cùng đối tượng, và phương thức thay đổi trường của đối tượng ấy.
2. Không. Nó chỉ đổi giá trị của biến cục bộ.
3. `Integer` bất biến; kết quả phép cộng được gán vào biến vòng lặp, không được ghi trở lại danh sách.
4. Không. Thao tác thay đổi tham chiếu ở vị trí danh sách; các biến khác giữ nguyên giá trị tham chiếu của mình.
5. Không. Khả năng sửa danh sách và khả năng sửa đối tượng phần tử là hai cấp khác nhau.

Hãy theo dõi riêng ba nơi: biến vòng lặp, tham chiếu được collection lưu và trạng thái đối tượng mà tham chiếu dẫn tới. Khi biết câu lệnh đang sửa nơi nào, tác động của `for-each` sẽ trở nên rõ ràng.
