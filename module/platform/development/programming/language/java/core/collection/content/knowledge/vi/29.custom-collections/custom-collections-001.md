# Khi nào cần tự cài đặt collection

## 1. Quyết định bắt đầu từ yêu cầu chưa được đáp ứng

Tự cài đặt collection nghĩa là chịu trách nhiệm cho một kiểu tập hợp dữ liệu có hợp đồng sử dụng rõ ràng: cách chứa hoặc biểu diễn phần tử, cách truy cập, duyệt, so sánh và thay đổi khi được phép.

Việc một bài toán có nhiều phần tử chưa đủ để cần một collection mới. Thường có ba lựa chọn khác nhau:

1. Dùng collection có sẵn và cấu hình hoặc kết hợp chúng.
2. Viết một lớp nghiệp vụ chứa collection bên trong.
3. Cài đặt một giao diện collection bằng cách biểu diễn dữ liệu riêng hoặc tạo một cách nhìn mới.

Một lớp `TagCatalog` chứa `LinkedHashSet` không đồng nghĩa đã viết lại một cấu trúc set. Một lớp kế thừa `AbstractList` nhưng tính phần tử từ công thức có thể là một cài đặt `List` mới, dù không có mảng chứa toàn bộ phần tử.

Cần cân nhắc lựa chọn thứ ba khi có một khoảng trống cụ thể:

- Cách biểu diễn dữ liệu hiện có không phù hợp về bộ nhớ hoặc chi phí thao tác.
- Cần tích hợp dữ liệu hoặc một view vào API collection chuẩn.
- Có ngữ nghĩa tập hợp hợp lệ mà các lựa chọn sẵn có chưa đáp ứng.
- Có yêu cầu đo được, có thể kiểm chứng, đủ giá trị để duy trì một cài đặt riêng.

Sau đó còn phải trả lời: có thực hiện đúng hợp đồng giao diện, kiểm tra được các đường sử dụng và chịu trách nhiệm bảo trì được không?

Mục tiêu không phải tránh mọi mã tự viết. Mục tiêu là chọn đúng phần cần tự sở hữu. Nếu thiếu chỉ một quy tắc nghiệp vụ, chưa nên mặc định nhận luôn trách nhiệm cho toàn bộ `List`, `Set` hoặc `Map`.

Bài dùng Java 17 trở lên. Bốn chương trình bên dưới độc lập, có tên tệp, lệnh biên dịch và stdout. Chúng minh họa các mức lựa chọn, một lỗi kế thừa có chủ ý và một trường hợp cài đặt collection có lý do rõ.

## 2. Kiểm tra công cụ có sẵn trước

### 2.1. Nhu cầu thường có một giải pháp gần hơn

| Yêu cầu thực tế | Điều nên kiểm tra trước khi viết collection mới |
|---|---|
| Chỉ cho bên nhận đọc | View không cho sửa hoặc bản sao không cho sửa |
| Cần một danh sách kết quả cố định sau khi chụp | Factory sao chép phù hợp và chính sách dữ liệu con |
| Cần một API hàng đợi theo LIFO từ deque | Bộ chuyển đổi giao diện có sẵn |
| Cần thứ tự duyệt theo lần thêm | Cài đặt có thứ tự duyệt phù hợp |
| Tập phần tử chỉ thuộc một kiểu enum | `EnumSet` |
| Tập vị trí số nguyên không âm có thể biểu diễn bằng bit | `BitSet`, nếu API bit phù hợp |
| Cần ràng buộc nghiệp vụ và tên thao tác riêng | Lớp nghiệp vụ bọc collection |

`EnumSet` là set chuyên cho các hằng thuộc một kiểu enum. `BitSet` là vector bit đánh chỉ số bằng số nguyên không âm; nó không trực tiếp triển khai `Set<Integer>`. Cần so cả khả năng biểu diễn lẫn giao diện mà bên gọi thật sự cần. Xem [EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html) và [BitSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html).

Một cấu trúc sẵn có đáp ứng đúng yêu cầu giúp giảm lượng hợp đồng phải tự quản lý. Đó là lợi ích về khả năng kiểm chứng và bảo trì, không chỉ số dòng mã.

### 2.2. Chương trình với view, bản sao và bộ chuyển đổi

Tệp `ExistingToolsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Queue;

public class ExistingToolsDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("alpha", "beta"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("gamma");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        try {
            view.add("delta");
        } catch (UnsupportedOperationException ex) {
            System.out.println("viewWrite=" + ex.getClass().getSimpleName());
        }

        Queue<String> stackView =
                Collections.asLifoQueue(new ArrayDeque<String>());
        stackView.offer("A");
        stackView.offer("B");
        System.out.println("lifo=" + stackView.poll() + "," + stackView.poll());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ExistingToolsDemo.java
java ExistingToolsDemo
```

Stdout:

```text
view=[alpha, beta, gamma]
snapshot=[alpha, beta]
viewWrite=UnsupportedOperationException
lifo=B,A
```

View `unmodifiableList` không cho sửa thông qua view nhưng vẫn đọc từ nguồn. Khi nguồn thêm `"gamma"`, view phản ánh thay đổi đó.

`List.copyOf` tạo một danh sách không phản ánh các thay đổi cấu trúc sau này của nguồn. Trong ví dụ chỉ có chuỗi bất biến, nên dễ quan sát sự khác biệt. Sao chép cấu trúc không tự là sao chép sâu các đối tượng phần tử. Xem [unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) và [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Phần sau dùng `Collections.asLifoQueue` để nhìn một deque như hàng đợi LIFO. B được đưa sau và được lấy trước A. Nếu chỉ cần cách nhìn này, không cần tự cài một lớp queue với thuật toán lưu trữ mới.

Bài học từ ví dụ là phải phát biểu đúng yêu cầu. “Không cho sửa qua API trả về” và “kết quả không đổi theo nguồn” là hai điều khác nhau. Một collection tự viết không có đặc quyền bỏ qua khác biệt ấy.

### 2.3. Kết hợp cấu trúc chưa chắc là collection mới

Nếu cần vừa giữ thứ tự vừa tra cứu theo mã, có thể ứng dụng cần kết hợp các cấu trúc hoặc một lớp quản lý chỉ mục. Việc kết hợp ấy có chi phí nhất quán riêng: thêm, xóa hoặc thay dữ liệu phải cập nhật đúng các phần liên quan.

Tuy vậy, phần đó có thể nằm trong một lớp nghiệp vụ với vài thao tác rõ. Không bắt buộc phơi bày nó như một `List` hoặc `Map` mới.

Một API hẹp thường cho phép giữ ranh giới thay đổi rõ hơn. Bên gọi không được tùy ý thực hiện mọi phép cập nhật chỉ vì có tham chiếu đến một giao diện collection rộng.

## 3. Quy tắc nghiệp vụ thường phù hợp với lớp bọc

### 3.1. Khi tên thao tác nói nhiều hơn add và remove

Giả sử ứng dụng quản lý các thẻ văn bản:

- Bỏ khoảng trắng đầu/cuối.
- Chuẩn hóa chữ thường theo một quy tắc đã chọn.
- Không nhận giá trị trống.
- Không đăng ký trùng theo dạng đã chuẩn hóa.
- Trả danh sách theo thứ tự đăng ký.

Đó là một quy trình đăng ký với danh tính dữ liệu riêng. Bên gọi cần `register`, `isRegistered` và `snapshot`, chưa cần toàn bộ quyền thay thế từng vị trí, sửa qua iterator hay ghép sublist.

Tệp `DomainWrapperDemo.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class DomainWrapperDemo {
    static final class TagCatalog {
        private final LinkedHashSet<String> tags = new LinkedHashSet<>();

        private static String normalize(String input) {
            String value = Objects.requireNonNull(input, "input")
                    .strip().toLowerCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("tag must not be blank");
            }
            return value;
        }

        boolean register(String input) {
            return tags.add(normalize(input));
        }

        boolean isRegistered(String input) {
            return tags.contains(normalize(input));
        }

        List<String> snapshot() {
            return List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        var catalog = new TagCatalog();
        System.out.println("first=" + catalog.register(" Java "));
        System.out.println("duplicate=" + catalog.register("java"));
        System.out.println("second=" + catalog.register("SPRING"));
        List<String> before = catalog.snapshot();
        catalog.register("Gradle");

        System.out.println("before=" + before);
        System.out.println("now=" + catalog.snapshot());
        System.out.println("find=" + catalog.isRegistered(" JAVA "));
        try {
            catalog.register("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DomainWrapperDemo.java
java DomainWrapperDemo
```

Stdout:

```text
first=true
duplicate=false
second=true
before=[java, spring]
now=[java, spring, gradle]
find=true
invalid=IllegalArgumentException
```

Lớp dùng `LinkedHashSet` để giữ tính duy nhất và thứ tự đăng ký; thứ tự duyệt theo lần thêm là đặc tính sẵn có của lớp đó. Xem [LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

Hai đầu vào `" Java "` và `"java"` được quy về cùng một thẻ theo chính sách của `TagCatalog`. Kết quả `false` của lần đăng ký thứ hai là kết quả nghiệp vụ đã định nghĩa, không phải một thay đổi tự ý vào hợp đồng của một collection tổng quát.

Danh sách `before` được chụp trước khi đăng ký Gradle nên không thay đổi theo catalog. Collection nền không bị trả trực tiếp ra ngoài.

### 3.2. Lớp này chưa nhận trách nhiệm của Set

`TagCatalog` không công bố mình là `Set<String>`. Nó có thể định nghĩa cách chuẩn hóa đầu vào của riêng mình mà không khiến người nhận một `Set` chuẩn phải đoán lại ý nghĩa `contains` hoặc `equals`.

Nếu cố tạo một collection chỉ lưu chuỗi đã chuẩn hóa, cần xem lại toàn bộ hợp đồng. Chẳng hạn, nếu `add(" Java ")` trả bình thường nhưng `contains(" Java ")` lại là `false`, không thể coi đó là cài đặt `Collection.add` thông thường đã đáp ứng yêu cầu.

Một lớp bọc cũng giúp hạn chế đường sửa: mọi đăng ký đi qua một hàm chuẩn hóa duy nhất, thay vì phải theo dõi hàng loạt phương thức thay đổi dữ liệu của một lớp cha công khai.

### 3.3. Phạm vi ví dụ cần được giữ rõ

Ví dụ dùng trong một luồng, không cung cấp hợp đồng đồng thời. Dùng một cấu trúc có sẵn bên trong không tự làm mọi phương thức của lớp bọc an toàn khi nhiều luồng gọi.

`Locale.ROOT` là một lựa chọn chuẩn hóa trong ví dụ. Định nghĩa danh tính thẻ của sản phẩm thực có thể cần quy tắc khác; đó là việc phải phát biểu trước khi chọn collection nền.

Nếu sau này cần thêm “đổi tên thẻ” hoặc “hợp nhất thẻ”, có thể thêm thao tác nghiệp vụ với ranh giới riêng. Không cần mở toàn bộ các phép sửa của set cho mọi bên gọi.

## 4. Những lý do thực sự có thể dẫn đến cài đặt mới

### 4.1. Biểu diễn đặc biệt nhưng vẫn cần giao diện chuẩn

Một dãy số có thể được xác định bằng phần tử đầu, bước và số lượng. Nếu bên gọi cần một `List<Integer>` để truy cập theo vị trí, không nhất thiết phải tạo và giữ sẵn mọi số.

Đây là một lý do cụ thể cho cài đặt mới: giữ một mô tả ngắn, tính giá trị khi được hỏi, nhưng vẫn có số lượng hữu hạn và thứ tự vị trí rõ ràng.

Các dạng biểu diễn nén, vùng dữ liệu riêng hoặc view tính toán cũng có thể thuộc nhóm này. Mỗi trường hợp phải nêu được ngữ nghĩa của dữ liệu và chi phí những thao tác API có thể kích hoạt.

### 4.2. Mô hình thao tác chưa được cấu trúc sẵn có đáp ứng

Nếu dữ liệu có cách truy cập đặc biệt, một thuật toán hoặc chỉ mục riêng có thể cần thiết. Nhưng trước khi triển khai, phải mô tả tải:

- Thao tác nào xảy ra thường xuyên?
- Tỷ lệ đọc, thêm, xóa là bao nhiêu?
- Dữ liệu lớn đến đâu?
- Chi phí đang gặp nằm ở cấu trúc hay ở xử lý bên ngoài?
- Giải pháp mới cải thiện đại lượng nào và đánh đổi điều gì?

“Có vẻ nhanh hơn” chưa là yêu cầu đủ rõ. Nếu đo cho thấy chi phí nằm ở truy vấn mạng hoặc dữ liệu đầu vào, viết lại collection có thể không giải quyết vấn đề chính.

### 4.3. Tạo view để tương thích với thư viện khác

Một thư viện có thể yêu cầu `List` trong khi ứng dụng giữ dữ liệu theo một biểu diễn khác. Một view phù hợp có thể giúp tích hợp mà không sao chép toàn bộ.

Lợi ích đó đi kèm các câu hỏi: view phản ánh thay đổi nguồn hay cố định, có được sửa không, ai giữ nguồn sống, các phép duyệt và `size` có tốn I/O không?

Không dùng `List` chỉ để giấu một nguồn không có số lượng hay vòng đời phù hợp. Nếu dữ liệu cần đóng tài nguyên hoặc chỉ có thể đọc một lượt, một API mô tả đúng vòng đời có thể rõ hơn một collection trông như truy cập trong bộ nhớ.

### 4.4. Học cấu trúc dữ liệu là một mục tiêu khác

Tự viết để học thuật toán, kiểm tra bất biến hoặc hiểu iterator là mục tiêu hợp lệ. Cần ghi rõ đó là cài đặt phục vụ thí nghiệm, với khả năng và giới hạn đã biết.

Một cấu trúc chạy đúng vài ví dụ học tập chưa tự trở thành lựa chọn thay thế cho thư viện đã được sử dụng rộng rãi. Mức kiểm chứng, tài liệu và trách nhiệm bảo trì phải tương ứng với nơi định dùng.

Không đánh giá thành công chỉ bằng việc tên lớp đã giống một collection chuẩn hoặc đã biên dịch được.

## 5. Chi phí lớn nhất là hợp đồng mà bên gọi được quyền dựa vào

### 5.1. Giao diện không chỉ là danh sách chữ ký phương thức

Khi một đối tượng được đưa cho mã khác dưới kiểu `List`, bên nhận có quyền sử dụng các phép toán đúng hợp đồng `List`, không chỉ các phép mà tác giả đã dùng trong một bài kiểm tra.

Các nhóm cần xác định gồm:

| Nhóm | Câu hỏi phải trả lời |
|---|---|
| Tập phần tử | Có trùng, có `null`, có giới hạn miền dữ liệu không? |
| Thứ tự | Theo vị trí, theo comparator, theo lần thêm hay không hứa thứ tự? |
| Thay đổi | Hỗ trợ thêm, xóa, thay thế nào? Phép nào không được hỗ trợ? |
| Duyệt | Có đủ phần tử, đúng thứ tự và hành vi khi hết dữ liệu không? |
| So sánh | `equals` và `hashCode` có đúng với giao diện cụ thể không? |
| Cách nhìn liên quan | Iterator, sublist hoặc view map có quan hệ gì với nguồn? |
| Chi phí | `get`, `contains`, `size`, `toArray` và duyệt tốn bao nhiêu? |
| Đồng thời | Có hỗ trợ nhiều luồng không, và ở mức bảo đảm nào? |

Một lớp chỉ thêm/xóa đúng chưa đủ nếu iterator bỏ phần tử, mảng trả về sai nội dung hoặc `equals` không đối xứng với một `List` hợp lệ khác.

### 5.2. Có thể giới hạn thao tác, nhưng phải giới hạn đúng cách

Collection được phép có các thao tác tùy chọn không được hỗ trợ; khi cần báo, dùng `UnsupportedOperationException` theo hợp đồng. Một collection không cho sửa vẫn là cài đặt hợp lệ nếu các khả năng còn lại đúng.

Giới hạn phần tử cũng có thể hợp lệ, chẳng hạn không nhận `null` hoặc không nhận một giá trị ngoài miền. Nhưng cần tài liệu và ngoại lệ đúng, không âm thầm bỏ phần tử.

Đặc biệt, `Collection.add` phải bảo đảm phần tử có mặt sau khi trở về bình thường. Nếu từ chối vì lý do khác việc đã có phần tử theo quy tắc không nhận trùng, phải báo ngoại lệ, không tùy ý trả `false`. Xem [hợp đồng Collection.add](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#add(E)).

Do đó, một “list có dung lượng tối đa” không được âm thầm bỏ lần thêm rồi báo như không có gì. Nếu thật sự muốn chính sách thử thêm trả `false` khi đầy, phải chọn một API có ngữ nghĩa phù hợp hoặc một thao tác nghiệp vụ riêng.

### 5.3. Không thay nghĩa giao diện để thuận tiện cho cài đặt

Một `List` phải có nghĩa vị trí và thứ tự phần tử phù hợp. Tự sắp xếp lại sau một phép chèn theo vị trí mà không giữ ý nghĩa hợp đồng không thể được biện minh chỉ bằng tên lớp `SortedList`.

Một `Set` cần giữ tính duy nhất và quy tắc so sánh bằng phù hợp với hợp đồng của set. Không chỉ dùng một cấu trúc có comparator rồi bỏ qua quan hệ với `equals`.

Một `Map` còn có các view khóa, giá trị và entry với quan hệ tới map. `Map` thuộc Java Collections Framework nhưng không phải giao diện con của `Collection`.

Không ép một kiểu có ngữ nghĩa khác vào giao diện chuẩn chỉ để truyền được cho một hàm. Nếu bên gọi phải học lại ý nghĩa cơ bản của hầu hết phương thức, có thể một API riêng phù hợp hơn.

## 6. Kế thừa lớp cụ thể có thể mở nhiều đường sửa hơn dự tính

### 6.1. Một override không tự bao phủ toàn bộ API

Nếu chỉ muốn thêm kiểm tra đầu vào, cách ngắn nhất nhìn có vẻ là kế thừa `ArrayList` rồi override `add`. Nhưng lớp cha còn `addAll`, `add(index, element)`, `set`, list iterator và các view liên quan.

Không có một nguyên tắc chung bảo đảm mọi phương thức thay đổi dữ liệu của lớp cha sẽ gọi đúng override mà tác giả chọn.

Tệp sau cố ý cài đặt thiếu để chứng minh vấn đề; không dùng nó làm lớp danh sách hợp lệ cho yêu cầu “không có chuỗi trắng”.

Tệp `IncompleteSubclassDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class IncompleteSubclassDemo {
    // Intentionally incomplete: overriding add does not protect all writes.
    static final class NonBlankList extends ArrayList<String> {
        @Override
        public boolean add(String value) {
            Objects.requireNonNull(value, "value");
            if (value.isBlank()) {
                throw new IllegalArgumentException("blank value");
            }
            return super.add(value);
        }
    }

    public static void main(String[] args) {
        var values = new NonBlankList();
        try {
            values.add("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("directAdd=" + ex.getClass().getSimpleName());
        }

        values.add("valid");
        values.addAll(List.of("   "));
        System.out.println("afterAddAllHasBlank=" +
                values.stream().anyMatch(String::isBlank));
        values.set(0, "");
        System.out.println("afterSetFirstLength=" + values.get(0).length());
        System.out.println("size=" + values.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 IncompleteSubclassDemo.java
java IncompleteSubclassDemo
```

Stdout:

```text
directAdd=IllegalArgumentException
afterAddAllHasBlank=true
afterSetFirstLength=0
size=2
```

Lần gọi `add("   ")` trực tiếp bị từ chối. Nhưng `addAll` đưa được chuỗi trắng vào, và `set` thay phần tử đầu bằng chuỗi rỗng.

Trên JDK 17 dùng để chạy ví dụ, `ArrayList.addAll` có đường xử lý riêng, không đi qua `add(E)` của lớp con cho từng phần tử. Có thể đối chiếu [cài đặt ArrayList trong OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/ArrayList.java).

Không cần biến chi tiết gọi nội bộ này thành cam kết cho mọi phiên bản. Điểm thiết kế quan trọng hơn là hợp đồng lớp cha không hứa một override duy nhất sẽ chặn mọi đường cập nhật của lớp con.

### 6.2. Sửa thêm vài phương thức vẫn cần xem toàn bộ bề mặt API

Có thể tiếp tục override thêm các phương thức thay đổi dữ liệu, nhưng phải xem cả:

- Các biến thể thêm và thêm theo lô.
- Thay thế theo vị trí và thay thế theo hàm.
- Thay đổi qua iterator hoặc list iterator.
- Thay đổi qua view được trả ra.
- Cách constructor khởi tạo dữ liệu.
- Hành vi kế thừa khi API thư viện phát triển.

Điều này không có nghĩa kế thừa luôn sai. Nó có nghĩa khi kế thừa một lớp cụ thể, phải biết những điểm mở rộng nào được thiết kế và được tài liệu hóa.

Nếu chỉ cần một vài thao tác nghiệp vụ như catalog ở mục trước, chứa cấu trúc bên trong có thể giữ đường sửa hẹp hơn và dễ kiểm tra hơn.

Nếu thật sự cần một collection mới, các lớp cài đặt khung giúp thể hiện rõ các thao tác nền mà phương thức khác được xây lên, thay vì dựa vào giả định về một lớp cụ thể.

## 7. Khi thực sự cần cài đặt: bắt đầu từ khung phù hợp

### 7.1. Các lớp khung giảm công việc lặp lại

| Kiểu cần cung cấp | Khung nên khảo sát | Phần nền cần hiểu |
|---|---|---|
| Collection tổng quát | `AbstractCollection` | Iterator và kích thước, cùng phép sửa nếu hỗ trợ |
| List truy cập theo vị trí hiệu quả | `AbstractList` | `get`, `size` và các phép sửa cần có |
| List dựa trên truy cập tuần tự | `AbstractSequentialList` | List iterator và kích thước |
| Set | `AbstractSet` | Cách giữ phần tử duy nhất, iterator và kích thước |
| Map | `AbstractMap` | `entrySet` và khả năng sửa đã công bố |

Đây là điểm bắt đầu để đọc hợp đồng, không phải bảng bảo đảm “chỉ cần viết vài phương thức là mọi yêu cầu đều tự đúng”.

`AbstractCollection` cung cấp nhiều thao tác từ iterator và kích thước. `AbstractSet` bổ sung ngữ nghĩa so sánh của set nhưng không tự biến một nguồn có phần tử trùng thành set hợp lệ. Xem [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) và [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

`AbstractSequentialList` xây thao tác vị trí trên list iterator, phù hợp hơn khi nguồn truy cập tuần tự. `AbstractMap` lấy `entrySet` làm phần nền cho nhiều khả năng. Xem [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html) và [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

Phải xem chi phí của phương thức kế thừa. Một cách viết đúng chức năng vẫn có thể không phù hợp nếu mọi `contains` phải quét một nguồn rất lớn hoặc mỗi lần `get` lại thực hiện I/O.

### 7.2. Trường hợp hợp lý: List tính từ mô tả dãy số

Giả sử dãy được xác định bởi:

```text
value(index) = first + index × step
index hợp lệ: từ 0 đến count - 1
```

Ta cần một danh sách hữu hạn, chỉ đọc, dùng được qua `List<Integer>`. Có thể lưu mô tả bằng ba tham số thay vì nạp sẵn toàn bộ giá trị.

`AbstractList` cho phép tạo một list không cho sửa bằng cách cài `get(int)` và `size()`; iterator và nhiều thao tác khác được xây trên những thao tác nền đó. Xem [AbstractList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

Tệp `ComputedListDemo.java`:

```java
import java.util.AbstractList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.RandomAccess;

public class ComputedListDemo {
    static final class ProgressionList extends AbstractList<Integer>
            implements RandomAccess {
        private final int first;
        private final int step;
        private final int count;

        ProgressionList(int first, int step, int count) {
            if (count < 0) {
                throw new IllegalArgumentException("negative count");
            }
            if (count > 0) {
                long last = first + (long) (count - 1) * step;
                if (last < Integer.MIN_VALUE || last > Integer.MAX_VALUE) {
                    throw new IllegalArgumentException("values exceed int range");
                }
            }
            this.first = first;
            this.step = step;
            this.count = count;
        }

        @Override
        public Integer get(int index) {
            Objects.checkIndex(index, count);
            return Math.toIntExact(first + (long) index * step);
        }

        @Override
        public int size() {
            return count;
        }
    }

    public static void main(String[] args) {
        List<Integer> values = new ProgressionList(10, 3, 5);
        List<Integer> reference = List.of(10, 13, 16, 19, 22);
        System.out.println("values=" + values);
        System.out.println("get2=" + values.get(2));
        System.out.println("subList=" + values.subList(1, 4));
        System.out.println("equalsForward=" + values.equals(reference));
        System.out.println("equalsBackward=" + reference.equals(values));
        System.out.println("sameHash=" +
                (values.hashCode() == reference.hashCode()));
        System.out.println("array=" + Arrays.toString(values.toArray()));
        System.out.println("sum=" +
                values.stream().mapToInt(Integer::intValue).sum());

        var large = new ProgressionList(0, 1, 1_000_000);
        System.out.println("largeSize=" + large.size());
        System.out.println("largeLast=" + large.get(large.size() - 1));
        System.out.println("descending=" + new ProgressionList(10, -2, 3));
        System.out.println("repeated=" + new ProgressionList(5, 0, 3));
        System.out.println("emptyHasNext=" +
                new ProgressionList(7, 1, 0).iterator().hasNext());

        try {
            values.add(25);
        } catch (UnsupportedOperationException ex) {
            System.out.println("write=" + ex.getClass().getSimpleName());
        }
        try {
            values.get(5);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("badIndex=" + ex.getClass().getSimpleName());
        }
        try {
            new ProgressionList(Integer.MAX_VALUE, 1, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("overflow=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComputedListDemo.java
java ComputedListDemo
```

Stdout:

```text
values=[10, 13, 16, 19, 22]
get2=16
subList=[13, 16, 19]
equalsForward=true
equalsBackward=true
sameHash=true
array=[10, 13, 16, 19, 22]
sum=80
largeSize=1000000
largeLast=999999
descending=[10, 8, 6]
repeated=[5, 5, 5]
emptyHasNext=false
write=UnsupportedOperationException
badIndex=IndexOutOfBoundsException
overflow=IllegalArgumentException
```

### 7.3. Vì sao đây là một cài đặt collection có căn cứ?

Biểu diễn trong lớp không phải một `ArrayList` được giấu dưới tên mới. Nó giữ mô tả dãy và tính phần tử theo chỉ số. Constructor không tạo một triệu đối tượng số để thiết lập dãy `large`.

Mọi vị trí có nghĩa rõ, số lượng hữu hạn, thứ tự ổn định và các giá trị được xác định từ dữ liệu không thay đổi. Giao diện `List` phù hợp với điều bên gọi được cung cấp.

Ví dụ cũng không tự viết lại iterator, `equals`, `hashCode`, `toArray` hoặc `subList`. Nó dùng phần khung và kiểm chứng một số tương tác quan trọng:

- Nội dung theo vị trí đúng.
- So sánh với một list chuẩn đúng ở cả hai chiều.
- List bằng nhau có hash bằng nhau.
- View theo khoảng và mảng có đúng nội dung.
- Stream nhận được toàn bộ các giá trị để tính tổng.
- Ghi không được hỗ trợ.
- Chỉ số sai và dãy vượt miền số được từ chối.

### 7.4. Kiểm tra biên và tràn số là một phần của thiết kế

`count` âm không có nghĩa hợp lệ nên constructor từ chối. Khi có phần tử, phần tử cuối được tính bằng `long` để tránh phép nhân trung gian tràn `int`.

Với một dãy tuyến tính, mọi giá trị nằm giữa giá trị đầu và cuối. Nếu hai đầu nằm trong miền `int`, các giá trị trung gian cũng nằm trong miền ấy. Vì thế kiểm tra đầu cuối phù hợp với biểu diễn này.

`get` dùng `Objects.checkIndex` trước khi tính. Không trả một giá trị mặc định cho chỉ số sai, vì như vậy sẽ giấu lỗi của bên gọi và làm sai ngữ nghĩa vị trí.

Bước âm tạo dãy giảm, bước 0 tạo phần tử trùng; cả hai đều có ý nghĩa với list trong ví dụ. Không vô tình áp một điều kiện “tăng nghiêm ngặt” chỉ vì mẫu dữ liệu đầu tiên đang tăng.

### 7.5. Lợi ích biểu diễn không làm mọi phép toán thành O(1)

`get` và `size` của ví dụ có công việc không tăng theo số phần tử. Vì vậy lớp dùng `RandomAccess` để biểu thị khả năng truy cập vị trí nhanh. Marker này giúp thuật toán tổng quát chọn cách làm phù hợp; nó không tự tăng tốc một cài đặt chậm. Xem [RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html).

Ngược lại, in toàn bộ dãy, tạo mảng, tính hash hoặc duyệt để tìm kiếm có thể phải đi qua nhiều phần tử. `toArray` trên dãy một triệu phần tử vẫn tạo một mảng đủ chứa kết quả.

Các giá trị được trả về dưới kiểu `Integer`; biểu diễn tính toán không loại bỏ mọi chi phí boxing khi API dùng kiểu đối tượng.

Phạm vi ví dụ là dãy hữu hạn chỉ đọc với quy tắc đơn giản. Nó chưa phải một thư viện số đầy đủ hoặc một lời hứa rằng mọi cài đặt `List` tính toán đều có cùng đặc tính.

## 8. Bằng chứng cần có trước khi dùng một cài đặt riêng

### 8.1. Kiểm chứng hợp đồng trước tối ưu hóa

Một kế hoạch kiểm tra có giá trị nên dựa vào hành vi mà bên gọi được quyền dùng, không chỉ sao lại thuật toán nội bộ.

Với list, có thể so một cài đặt mới với list tham chiếu qua các thao tác đã công bố: thêm/xóa/thay thế nếu hỗ trợ, truy cập biên, duyệt, mảng, so sánh và view.

Với cấu trúc chuyên biệt, không phải mọi hành vi đều giống một collection chuẩn bất kỳ. Phải xác định phần tương đương và phần có hạn chế hợp lệ, rồi kiểm tra đúng những gì đã hứa.

Ví dụ `ProgressionList` không cần giả vờ hỗ trợ thêm/xóa. Điều phải kiểm tra là nó chỉ đọc đúng cách, nội dung và phép đọc vẫn hợp lệ với `List`.

### 8.2. Iterator là một API thật, không chỉ một vòng for

Nếu tự cài iterator, cần tuân thủ trạng thái: `hasNext`, `next` khi còn/hết dữ liệu, và `remove` nếu được hỗ trợ. Khi hết lượt, `Iterator.next()` phải báo `NoSuchElementException`; không dùng `null` làm dấu kết thúc. Xem [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Với list có thể thay đổi, còn phải xác định hành vi khi cấu trúc đổi trong lúc duyệt. Nếu dùng cơ chế `modCount` của `AbstractList`, cần cập nhật đúng theo thiết kế của khung. Cơ chế phát hiện sửa đổi không phải một khóa đồng bộ nhiều luồng.

Nếu tự tối ưu spliterator hoặc stream, không khai báo các đặc tính về thứ tự, kích thước hay tính bất biến chỉ để thuật toán chạy nhanh hơn. Những đặc tính đó phải đúng với dữ liệu và cách cập nhật.

Một cài đặt đúng nhờ dùng iterator kế thừa thường dễ kiểm chứng hơn một iterator tự viết chưa có yêu cầu đặc biệt.

### 8.3. Kiểm tra mọi đường sửa và cả trường hợp thất bại

Với lớp có điều kiện miền dữ liệu, cần kiểm tra `addAll`, cập nhật theo vị trí, iterator, view và các phương thức mặc định liên quan. Ví dụ kế thừa thiếu ở trên cho thấy chỉ thử đường `add` là không đủ.

Nếu thao tác theo lô gặp phần tử không hợp lệ, trạng thái sau lỗi phải phù hợp với điều đã công bố. Không tự giả định hợp đồng collection luôn đảm bảo hoàn tác tất cả phần đã làm trước khi ném lỗi.

Nếu nghiệp vụ yêu cầu một nhóm thay đổi phải cùng thành công hoặc cùng thất bại, phải thiết kế ranh giới đó rõ ràng. Đó có thể là lý do dùng một phương thức nghiệp vụ riêng thay vì hứa ngầm bằng tên `addAll`.

Với phép tùy chọn không làm thay đổi gì, việc có ném `UnsupportedOperationException` hay không có thể phụ thuộc hợp đồng cụ thể. Khi kiểm thử, đọc đúng API đã chọn thay vì đưa ra một quy tắc chung quá rộng cho mọi collection chỉ đọc.

### 8.4. Hiệu năng phải được so với phương án thay thế thật

Một cài đặt mới nên được đối chiếu với cấu trúc sẵn có đã cấu hình phù hợp, dữ liệu và tải đại diện. Không chỉ đo trường hợp mà thuật toán mới được thiết kế thuận lợi nhất.

Cần tính cả:

- Chi phí tạo và thu hồi dữ liệu.
- Thao tác thường gặp và thao tác hiếm nhưng đắt.
- Mức sử dụng bộ nhớ ở trạng thái thực.
- Độ trễ, không chỉ tổng số thao tác mỗi giây.
- Chi phí chuyển đổi khi đi qua API khác.
- Chi phí giữ view hoặc nguồn dữ liệu sống.

Ví dụ dãy tính toán chứng minh không phải nạp sẵn mọi giá trị để đọc một chỉ số. Chương trình không đo số byte hoặc so thông lượng, nên không dùng stdout của nó làm kết luận định lượng về hiệu năng.

## 9. Chốt quyết định bằng một mô tả thiết kế ngắn

Trước khi viết một collection mới, có thể ghi lại các điểm sau:

1. **Yêu cầu:** bên gọi cần những thao tác nào và với dữ liệu ra sao?
2. **Khoảng trống:** phương án sẵn có không đáp ứng chính xác điểm gì?
3. **Giao diện:** vì sao chọn `List`, `Set`, `Map`, `Collection`, hay chỉ một API riêng?
4. **Biểu diễn:** dữ liệu được lưu, tính hoặc lấy từ nguồn nào?
5. **Hợp đồng:** thứ tự, phần tử hợp lệ, khả năng sửa, view và vòng đời.
6. **Bằng chứng:** điều gì đã được kiểm chứng về chức năng, biên và chi phí?
7. **Trách nhiệm duy trì:** ai sẽ cập nhật khi yêu cầu hoặc môi trường thay đổi?

Các điểm này làm cho quyết định có thể được xem xét bằng yêu cầu và bằng chứng, thay vì chỉ bằng cảm giác mã ngắn hay thuật toán thú vị.

Áp vào các ví dụ:

| Trường hợp | Quyết định có căn cứ |
|---|---|
| Cần view không cho sửa, bản sao hoặc cách nhìn LIFO | Dùng công cụ có sẵn |
| Cần đăng ký thẻ với chuẩn hóa và quy tắc riêng | Dùng lớp nghiệp vụ bọc `LinkedHashSet` |
| Muốn cấm chuỗi trắng bằng cách override một `add` | Thiết kế chưa giữ được điều kiện trên mọi đường sửa |
| Cần `List<Integer>` hữu hạn được mô tả bằng công thức | Cài list chỉ đọc dựa trên `AbstractList` có thể phù hợp |

Nếu chưa mô tả được khoảng trống hoặc lợi ích cần kiểm chứng, nên tiếp tục tìm một cách kết hợp đơn giản hơn trước khi mở rộng bề mặt API.

Nếu ngữ nghĩa mới cố ý khác phần lớn hợp đồng chuẩn, một kiểu riêng có thể giúp người dùng hiểu đúng hơn việc gắn nhãn `List` hoặc `Set`.

Nếu cần nhiều luồng, dữ liệu ngoài heap, bộ nhớ nén hoặc xử lý tài nguyên ngoài, phạm vi kiểm chứng lớn hơn đáng kể. Không xem chúng là vài cờ có thể thêm vào sau một cài đặt tuần tự đã chạy thử.

## 10. Thực hành và tự kiểm tra

### Bài 1: có thật sự cần collection mới không?

Một dịch vụ cần trả danh sách cấu hình cho bên gọi, không cho bên gọi sửa. Sau khi trả, cấu hình nguồn có thể được cập nhật.

Hãy nêu hai yêu cầu khác nhau:

- Bên gọi luôn nhìn thấy cấu hình mới nhất qua một view.
- Bên gọi giữ đúng nội dung tại thời điểm đã chụp.

Vì sao không nên gộp cả hai thành “immutable list” rồi tự viết một lớp mới? Dùng `ExistingToolsDemo` để giải thích điều phải quyết định về quan hệ với nguồn và dữ liệu phần tử.

### Bài 2: nghiệp vụ hay Set?

Một bộ đăng ký mã cần chuẩn hóa chữ hoa/chữ thường, kiểm tra định dạng và có thao tác hợp nhất mã.

Bên gọi thật sự cần mọi phương thức của `Set` hay cần một vài thao tác đăng ký? Nếu triển khai trực tiếp `Set<String>`, phải giữ những nghĩa nào của `contains`, `equals` và giá trị được lưu?

Hướng giải thích: một API nghiệp vụ có thể mô tả danh tính đã chuẩn hóa rõ ràng. Chỉ nhận hợp đồng set khi có lý do tương thích và có thể giữ đúng hợp đồng đó.

### Bài 3: tìm đường sửa bị bỏ sót

Với `NonBlankList` trong ví dụ cố ý sai, hãy liệt kê thêm các đường sửa ngoài `add(E)`. Sau đó giải thích vì sao chỉ thêm một hoặc hai override mà không đọc lớp cha vẫn chưa là một chứng minh đầy đủ.

Không sửa bằng cách trả `false` cho mọi đầu vào không hợp lệ. Cần chọn đúng hợp đồng từ chối hoặc thu hẹp API.

### Bài 4: đánh đổi của danh sách tính toán

Với `ProgressionList`, đọc phần tử cuối của một dãy một triệu số không cần nạp sẵn tất cả giá trị. Vì sao gọi `toArray`, in toàn bộ hoặc tính hash vẫn có thể tốn nhiều công việc?

Nếu bên gọi chỉ cần một lần duyệt và không cần truy cập theo vị trí, giao diện nào hẹp hơn có thể đủ? Nếu phải tương thích một thư viện nhận `List`, vì sao cài đặt ví dụ lại có lý do rõ hơn?

Hướng giải thích: biểu diễn nén hoặc tính toán giúp một số thao tác, không thay đổi yêu cầu đầu ra của mọi thao tác tổng quát. Giao diện nên xuất phát từ cách sử dụng cần thiết.

### Bài 5: viết điều kiện để đồng ý duy trì cài đặt riêng

Chọn một yêu cầu thực của bản thân và ghi một mô tả ngắn theo bảy điểm ở mục trước.

Nếu bỏ collection tự viết đi, phương án có sẵn tốt nhất là gì? Nó thiếu điều gì? Cần những kiểm tra nào để chứng minh phương án mới giữ đúng nghĩa và tạo lợi ích?

Một câu trả lời có căn cứ cần nêu rõ phần phải tự sở hữu, phần có thể tái sử dụng và rủi ro đã được kiểm chứng đến đâu.

### Những câu hỏi cuối trước khi bắt đầu

1. Điều thiếu là cấu trúc dữ liệu, cách nhìn dữ liệu hay quy tắc nghiệp vụ?
2. Công cụ có sẵn hoặc lớp bọc có giải quyết được không?
3. Giao diện chuẩn có đúng với ngữ nghĩa cần cung cấp không?
4. Có biết toàn bộ đường đọc, duyệt và sửa mà giao diện mở ra không?
5. Đã chọn lớp khung phù hợp với cách truy cập chưa?
6. Lợi ích được giải thích bằng biểu diễn hoặc phép đo nào?
7. Có kiểm tra biên, ngoại lệ, so sánh và view không?
8. Phạm vi đồng thời, tài nguyên và bảo trì đã được phát biểu rõ chưa?

Tự cài đặt collection có giá trị khi nó lấp một khoảng trống cụ thể và vẫn giữ đúng điều bên gọi được quyền dựa vào. Lựa chọn lớp bọc hoặc công cụ có sẵn cũng là một quyết định thiết kế đầy đủ khi chúng đáp ứng đúng yêu cầu.
