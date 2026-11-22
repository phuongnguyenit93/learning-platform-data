# Khóa khả biến, hợp đồng equals–hashCode và lỗi mất dấu phần tử

## 1. Tại sao một phần tử vẫn ở trong Set nhưng lại không tìm thấy?

Giả sử ứng dụng đưa một khách hàng vào `HashSet<Customer>` để tránh trùng theo mã khách hàng. Sau đó, một đoạn mã đổi chính mã ấy. Khi duyệt Set, ứng dụng vẫn nhìn thấy khách hàng; nhưng `contains` hoặc `remove` có thể trả về `false`. Đối tượng không tự biến mất khỏi bộ nhớ. Thông tin dùng để tìm nó đã không còn khớp với thông tin lúc nó được đưa vào cấu trúc băm.

Bài này nằm trong chủ đề **Set dùng băm**. Mục tiêu là hiểu ba việc liên quan nhưng khác nhau:

- `equals` quyết định hai đối tượng có được xem là cùng một giá trị hay cùng một thực thể theo mô hình đã chọn.
- `hashCode` cung cấp mã băm nhất quán với cách xem bằng nhau đó.
- Trong thời gian một phần tử nằm trong Set, dữ liệu quyết định việc nhận diện nó phải giữ ổn định.

Từ **khóa** trong bài không có nghĩa Set chứa cặp khóa–giá trị như Map. Với `HashSet<E>`, bản thân phần tử `E` được dùng để tra cứu thành viên. Những trường mà `equals` và `hashCode` dựa vào tạo thành **khóa logic** của phần tử.

Ví dụ, nếu hai khách hàng được xem là bằng nhau khi có cùng `id`, thì `id` là dữ liệu định danh; tên hiển thị có thể chỉ là dữ liệu mô tả. Nếu hai tọa độ bằng nhau khi cả `x` và `y` bằng nhau, thì cặp `(x, y)` là dữ liệu nhận diện giá trị.

Cần phân biệt thêm **đồng nhất tham chiếu** và **bằng nhau theo giá trị**:

```java
a == b       // Hai biến có cùng trỏ tới một đối tượng không?
a.equals(b)  // Theo định nghĩa của lớp, hai đối tượng có bằng nhau không?
```

Đây là hai biểu thức minh họa, không phải chương trình độc lập. Một Set dùng `equals` không có nghĩa nó sẽ bỏ qua mã băm và quét mọi đối tượng bằng `==` mỗi lần tìm kiếm.

Hướng học phù hợp là: xác định quy tắc bằng nhau → hiểu điều kiện của mã băm → xem điều gì xảy ra khi khóa đổi → chọn thiết kế khóa ổn định → kiểm tra toàn bộ vòng đời của phần tử.

## 2. Hợp đồng equals–hashCode cần bảo vệ điều gì?

Với các tham chiếu khác `null`, `equals` cần có tính phản xạ, đối xứng, bắc cầu và nhất quán khi dữ liệu dùng so sánh không đổi; so sánh với `null` trả về `false`.

Điều kiện quan trọng của mã băm là:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

Chiều ngược lại không bắt buộc. Hai đối tượng không bằng nhau vẫn có thể trùng mã băm. Mã băm của một đối tượng cần ổn định trong một lần chạy khi thông tin dùng cho `equals` không đổi; không cần giữ nguyên giữa các lần chạy ứng dụng. Đây là hợp đồng của [Object.equals và Object.hashCode trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

Hai trường hợp sau phải được đọc khác nhau:

| Quan hệ giữa hai đối tượng | Quan hệ mã băm | Ý nghĩa |
|---|---|---|
| Bằng nhau | Cùng mã băm | Phù hợp với điều kiện bắt buộc |
| Bằng nhau | Khác mã băm | Lỗi triển khai hợp đồng |
| Không bằng nhau | Cùng mã băm | Va chạm băm; tự nó không phải lỗi đúng đắn |
| Không bằng nhau | Khác mã băm | Trường hợp bình thường |

Mã băm không phải số căn cước duy nhất của đối tượng. Không dùng một `Set<Integer>` chứa các giá trị `hashCode()` để thay cho `Set<Customer>` nếu cần khử trùng khách hàng: hai khách hàng khác nhau có thể bị gộp chỉ vì va chạm băm.

Khi viết `equals` theo `id`, một cách dễ kiểm tra là viết `hashCode` theo cùng `id`. Không được đưa thêm một trường có thể khác giữa hai đối tượng bằng nhau vào mã băm theo cách làm chúng ra hai kết quả khác nhau. Ví dụ, `equals` chỉ xét `id` nhưng `hashCode` còn xét `displayName` sẽ gây lỗi khi hai tên khác nhau vẫn thuộc cùng một `id`.

Ngược lại, mã băm không nhất thiết phải chứa mọi trường của `equals`. Nó có thể dùng ít thông tin hơn và vẫn thỏa điều kiện một chiều ở trên, nhưng dễ tạo nhiều va chạm hơn. Vì vậy, cần đánh giá cả tính đúng đắn lẫn phân bố, thay vì coi “băm tất cả trường” là một quy tắc áp dụng máy móc.

## 3. Hợp đồng của lớp và điều kiện sử dụng Set là hai tầng khác nhau

Một lớp khả biến có thể triển khai `equals` và `hashCode` hợp lý tại từng thời điểm:

```java
// Trích đoạn minh họa trong một lớp có trường int code.
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof Key key && code == key.code);
}

@Override
public int hashCode() {
    return Integer.hashCode(code);
}
```

Nếu `code` đổi từ `1` thành `2`, cả quan hệ bằng nhau lẫn mã băm đổi theo dữ liệu mới. Không thể chỉ nhìn thấy mã băm đổi rồi kết luận mọi lớp như vậy đều vi phạm hợp đồng của `Object`: hợp đồng có điều kiện liên quan đến việc dữ liệu dùng so sánh có thay đổi hay không.

Vấn đề xuất hiện khi đối tượng ấy đang là phần tử của một Set. Tài liệu [Set của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) nêu rằng hành vi của Set không được đặc tả nếu giá trị phần tử bị thay đổi theo cách ảnh hưởng đến so sánh `equals` trong lúc nó đang ở trong Set.

Vì vậy, cần kiểm tra hai tầng:

1. **Tầng lớp:** hai đối tượng bằng nhau có luôn cho cùng mã băm, các tính chất của `equals` có đúng không?
2. **Tầng vòng đời trong cấu trúc:** dữ liệu quyết định bằng nhau có bị sửa từ khi thêm đến khi gỡ phần tử khỏi Set không?

Một lớp có thể vượt qua kiểm tra tầng thứ nhất nhưng vẫn được sử dụng sai ở tầng thứ hai. Đó là lý do một bộ kiểm thử chỉ tạo hai đối tượng, gọi `equals`, rồi kết thúc chưa đủ để phát hiện lỗi mất dấu.

Cũng không nên cấm mọi thay đổi trên mọi phần tử. Nếu định danh chỉ phụ thuộc vào một `id` ổn định, đổi ghi chú hoặc tên hiển thị không tham gia `equals`–`hashCode` có thể phù hợp. Điều cần giữ ổn định là **ngữ nghĩa nhận diện**, không nhất thiết toàn bộ trạng thái của đối tượng.

## 4. Cấu trúc băm giữ tham chiếu nhưng không theo dõi setter

`HashSet` được hỗ trợ bởi một `HashMap`, theo [tài liệu HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html). Có thể hình dung thao tác thêm và tìm như sau:

```text
Khi thêm:
    đọc khóa logic hiện tại
        -> tính mã băm
        -> chọn vùng tìm kiếm
        -> kiểm tra phần tử phù hợp
        -> lưu một mục chứa tham chiếu tới đối tượng

Khi tìm hoặc xóa bằng đối tượng:
    đọc khóa logic tại thời điểm gọi
        -> tính mã băm hiện tại
        -> tìm trong vùng tương ứng
        -> kiểm tra phần tử ứng viên
```

Trong triển khai [HashMap của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java), một mục giữ mã băm đã tính khi tạo và tham chiếu khóa. Tra cứu tính lại mã băm từ đối tượng được đưa vào, kiểm tra mã băm của mục rồi mới xét tham chiếu hoặc `equals`. Thay đổi trường của đối tượng không tự cập nhật mục đã lưu.

Sơ đồ này chỉ là mô hình phục vụ hiểu lỗi:

```text
Thời điểm thêm:
    đối tượng K: code = 1
    mục lưu: tham chiếu K, thông tin băm từ code = 1

Sau khi gọi setter:
    đối tượng K: code = 2
    mục cũ: vẫn giữ thông tin băm lúc thêm

Khi contains(K):
    yêu cầu tìm sử dụng thông tin băm từ code = 2
```

Không cần học thuộc số ngăn hoặc công thức nội bộ để tránh lỗi. Chỉ cần nhận ra rằng một chỉ mục được tạo theo thông tin cũ không tự điều chỉnh khi đối tượng được sửa qua một tham chiếu khác.

Đặc biệt, `==` đúng giữa đối tượng cần tìm và đối tượng đã lưu không bảo đảm tra cứu sẽ thành công: bước tìm vùng ứng viên và kiểm tra mã băm có thể đã loại mục cũ trước đó.

Cũng không nên kết luận “hai mã băm cùng rơi vào một ngăn là an toàn”. Trong triển khai được mô tả, mã băm lưu ở từng mục còn tham gia kiểm tra. Quan trọng hơn, việc nhận diện thành viên đã bị thay đổi thì điều kiện sử dụng Set đã không còn được bảo vệ.

## 5. Chương trình 1: phần tử mất dấu rồi cùng tham chiếu được thêm lần nữa

Lưu tệp `MutableKeyFailureDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class MutableKeyFailureDemo {
    static final class Key {
        private int code;

        Key(int code) {
            this.code = code;
        }

        void changeCode(int newCode) {
            code = newCode;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Key key && code == key.code);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(code);
        }
    }

    public static void main(String[] args) {
        Key key = new Key(1);
        Set<Key> keys = new HashSet<>();
        keys.add(key);

        System.out.println("contains before change = " + keys.contains(key));
        key.changeCode(2);
        System.out.println("size after change = " + keys.size());

        long references = 0;
        for (Key stored : keys) {
            if (stored == key) {
                references++;
            }
        }
        System.out.println("same reference seen by iteration = " + references);
        System.out.println("contains after change = " + keys.contains(key));
        System.out.println("remove after change = " + keys.remove(key));
        System.out.println("add same reference again = " + keys.add(key));
        System.out.println("size after re-add = " + keys.size());

        references = 0;
        for (Key stored : keys) {
            if (stored == key) {
                references++;
            }
        }
        System.out.println("same reference occurrences = " + references);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 MutableKeyFailureDemo.java
java MutableKeyFailureDemo
```

Kết quả của lần chạy kiểm chứng:

```text
contains before change = true
size after change = 1
same reference seen by iteration = 1
contains after change = false
remove after change = false
add same reference again = true
size after re-add = 2
same reference occurrences = 2
```

Đây là **thí nghiệm cố ý dùng sai Set**. Mã dùng ngôn ngữ và API có ở Java 17 trở lên. Các kết quả đã được chạy kiểm chứng bằng Azul OpenJDK 24.0.2 sau khi biên dịch với `--release 17`; cơ chế được đối chiếu với mã nguồn OpenJDK 17. Những dòng sau khi đổi khóa là quan sát của triển khai này, không phải lời hứa rằng mọi triển khai Set hoặc mọi dữ liệu sai sẽ cho cùng kết quả.

### 5.1. Vì sao size vẫn bằng 1?

Lời gọi `key.changeCode(2)` chỉ sửa đối tượng. Nó không gọi `keys.remove`, không gọi `keys.add` và không làm Set chủ động đếm lại các lớp tương đương. Mục đã lưu vẫn tồn tại.

Vòng lặp thấy cùng tham chiếu một lần. Điều đó giúp xác định rằng đối tượng chưa bị gỡ khỏi các mục của cấu trúc. Nó không chứng minh đường tra cứu theo mã băm hiện tại còn đúng.

### 5.2. Vì sao contains và remove cùng thất bại?

Hai thao tác đều được gọi bằng khóa đã đổi. Trong ví dụ này, đường tìm hiện tại không khớp mục được tạo lúc `code = 1`. Do đó, cả kiểm tra lẫn xóa bằng đối tượng đều không tìm được mục cũ.

Không nên “sửa” bằng cách thay `remove(key)` thành `remove(new Key(2))`: đối tượng thăm dò mới cũng mô tả định danh mới và dùng mã băm mới. Vấn đề nằm ở trạng thái chỉ mục cũ, không nằm ở việc có dùng đúng biến tham chiếu hay không.

### 5.3. Vì sao add lại cùng tham chiếu có thể tạo size bằng 2?

Lần `add` sau dùng thông tin băm mới. Trong lần chạy này, nó không phát hiện mục cũ và tạo thêm một mục nữa trỏ vào chính đối tượng ấy. Khi duyệt, cùng tham chiếu được gặp hai lần.

Đây không phải khả năng hợp lệ để khai thác như một Set chứa phần tử trùng. Nó là hậu quả quan sát được sau khi chương trình đã thay đổi thông tin nhận diện của phần tử trong Set.

Điểm thực hành quan trọng là: **không chữa phần tử mất dấu bằng cách add lại**. Việc đó có thể làm trạng thái khó giải thích hơn, thay vì khôi phục tính duy nhất.

### 5.4. Vì sao không có ConcurrentModificationException?

Đổi trường `code` không tương đương với thao tác cấu trúc như thêm hoặc gỡ một mục qua Set. Không có cơ chế chung buộc mọi setter của phần tử phải thông báo cho iterator.

Một chương trình không ném ngoại lệ vẫn có thể đang dùng sai điều kiện của cấu trúc dữ liệu. Không dùng việc “vòng lặp chạy xong bình thường” làm bằng chứng rằng mọi khóa đều còn tìm được.

## 6. Chương trình 2: hợp đồng sai khác với va chạm băm hợp lệ

Ví dụ tiếp theo đặt cạnh nhau hai loại:

- `BrokenKey` so sánh theo `id`, nhưng cho phép hai đối tượng cùng `id` có mã băm khác nhau. Nó sai ngay từ thiết kế, dù mọi trường đều `final`.
- `CollidingKey` là record có định danh theo `id`, nhưng cố ý trả về mã băm `0` cho mọi giá trị. Phân bố này kém, nhưng điều kiện “bằng nhau thì cùng mã băm” vẫn đúng.

Lưu tệp `EqualityHashContractDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class EqualityHashContractDemo {
    static final class BrokenKey {
        private final int id;
        private final int suppliedHash;

        BrokenKey(int id, int suppliedHash) {
            this.id = id;
            this.suppliedHash = suppliedHash;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof BrokenKey key && id == key.id);
        }

        @Override
        public int hashCode() {
            return suppliedHash;
        }
    }

    record CollidingKey(int id) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey(7, 1);
        BrokenKey b = new BrokenKey(7, 2);
        Set<BrokenKey> broken = new HashSet<>();

        System.out.println("broken keys equal = " + a.equals(b));
        System.out.println("broken hashes equal = "
                + (a.hashCode() == b.hashCode()));
        System.out.println("add broken a = " + broken.add(a));
        System.out.println("add broken b = " + broken.add(b));
        System.out.println("broken set size = " + broken.size());

        CollidingKey x = new CollidingKey(1);
        CollidingKey y = new CollidingKey(2);
        Set<CollidingKey> valid = new HashSet<>();

        System.out.println("collision keys equal = " + x.equals(y));
        System.out.println("collision hashes equal = "
                + (x.hashCode() == y.hashCode()));
        System.out.println("add collision x = " + valid.add(x));
        System.out.println("add collision y = " + valid.add(y));
        System.out.println("contains equal probe = "
                + valid.contains(new CollidingKey(1)));
        System.out.println("add equal probe = "
                + valid.add(new CollidingKey(1)));
        System.out.println("valid set size = " + valid.size());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 EqualityHashContractDemo.java
java EqualityHashContractDemo
```

Kết quả của lần chạy kiểm chứng:

```text
broken keys equal = true
broken hashes equal = false
add broken a = true
add broken b = true
broken set size = 2
collision keys equal = false
collision hashes equal = true
add collision x = true
add collision y = true
contains equal probe = true
add equal probe = false
valid set size = 2
```

Các dòng của `BrokenKey` minh họa một lớp vi phạm hợp đồng, không phải một cách tạo Set hợp lệ có hai thành viên bằng nhau. Kết quả của ví dụ lỗi đã được kiểm chứng trên môi trường nêu ở chương trình 1; không dùng kết quả ấy làm yêu cầu tương thích cho các thư viện khác.

Ở phần `CollidingKey`, `x` và `y` có cùng mã băm nhưng không bằng nhau nên cả hai được giữ. Khi thêm `new CollidingKey(1)`, Set nhận ra phần tử bằng nhau đã có và trả về `false`.

Từ ví dụ này có hai kết luận khác nhau:

1. Các trường `final` không tự làm cho một cặp `equals`–`hashCode` sai trở thành đúng.
2. Va chạm băm không cho phép bỏ qua `equals`; cũng không tự làm mất tính duy nhất nếu các điều kiện của cấu trúc được giữ.

Không chọn mã băm hằng trong mã thực tế chỉ để làm bài kiểm tra “hai giá trị bằng nhau có cùng hash” luôn qua. Bài kiểm tra đó là điều kiện cần; nó chưa đánh giá chất lượng phân bố hoặc việc thay đổi quan hệ bằng nhau trong thời gian phần tử nằm trong Set.

## 7. Vì sao các cách vá chỉ sửa hash vẫn chưa đủ?

### 7.1. Giữ hash hằng không giữ được ý nghĩa duy nhất

Giả sử lớp có `equals` theo một trường `code` khả biến nhưng `hashCode` luôn trả về `0`. Thêm hai đối tượng có mã `1` và `2` lúc đầu là hai thành viên khác nhau. Sau đó sửa mã của đối tượng thứ hai thành `1`.

Hai đối tượng bây giờ bằng nhau theo `equals`, mặc dù cấu trúc vẫn có hai mục đã được thêm trước đó. Set không chủ động hợp nhất chúng sau setter.

Ở đây, mã băm không hề đổi. Lỗi vẫn tồn tại vì **quan hệ bằng nhau đã đổi trong lúc các phần tử còn ở trong Set**. Do đó, yêu cầu “chỉ giữ hash ổn định là đủ” bỏ sót phần quan trọng nhất.

### 7.2. Lưu mã băm cũ trong một trường

Nếu `equals` đọc mã hiện tại nhưng `hashCode` trả về kết quả đã lưu từ mã cũ, một đối tượng thăm dò được tạo theo giá trị hiện tại có thể bằng đối tượng cũ nhưng lại cho mã băm khác. Cách vá này chuyển lỗi vòng đời thành cả lỗi nhất quán giữa hai phương thức.

Chỉ nên lưu sẵn mã băm khi dữ liệu quyết định bằng nhau đã bất biến hoặc đã được chụp thành giá trị ổn định phù hợp. Không dùng bộ nhớ đệm để che việc thay đổi định danh.

### 7.3. Dùng identityHashCode trong khi equals vẫn theo dữ liệu

Mã băm theo đồng nhất đối tượng không tự phù hợp với `equals` theo giá trị. Hai đối tượng khác tham chiếu có thể cùng `id` và được xem là bằng nhau, nhưng cách băm theo từng đối tượng không bảo đảm chúng có cùng kết quả.

Nếu mục tiêu của mô hình thực sự là đồng nhất tham chiếu, hãy thiết kế và chọn cấu trúc theo đúng mục tiêu ấy. Không ghép một nửa quy tắc theo giá trị với một nửa quy tắc theo tham chiếu để chữa một lỗi tra cứu.

### 7.4. Băm ngẫu nhiên hoặc băm theo thời gian

Nếu dữ liệu nhận diện không đổi mà mỗi lần gọi mã băm lại cho kết quả khác, lớp đã không đáp ứng hợp đồng ngay cả trước khi xét đến khả biến. Tra cứu không có cơ sở ổn định để tìm mục trước đó.

Nên sửa **mô hình nhận diện và vòng đời**, sau đó mới cải thiện phân bố mã băm. Việc thay công thức hash đơn lẻ không giải quyết được một định danh đang đổi ngoài sự kiểm soát của cấu trúc.

## 8. Chọn dữ liệu nào làm khóa logic?

Hai mô hình thường gặp cần được quyết định theo nghiệp vụ:

| Mô hình | Câu hỏi nhận diện | Dữ liệu phù hợp | Cách thay đổi |
|---|---|---|---|
| Giá trị | Hai giá trị có cùng nội dung quan trọng không? | Thành phần của giá trị, được giữ bất biến | Tạo giá trị mới |
| Thực thể | Hai đối tượng có đại diện cùng thực thể không? | Mã định danh ổn định, đã được xác lập | Đổi dữ liệu mô tả, giữ định danh |
| Bản chụp | Hai ảnh chụp tại thời điểm thu thập có cùng thông tin khóa không? | Thành phần đã sao chép và đóng băng đúng mức | Thu thập bản chụp mới |
| Đồng nhất tham chiếu | Có đúng là cùng một đối tượng không? | Ngữ nghĩa đồng nhất đối tượng | Chỉ dùng khi bài toán thật sự yêu cầu |

Không có quy tắc “mọi trường luôn thuộc equals” hoặc “chỉ một id luôn là đủ” cho mọi lớp. Ví dụ:

- Một khách hàng có thể đổi tên nhưng vẫn là cùng khách hàng.
- Một điểm tọa độ đổi `x` thì đã thành một giá trị tọa độ khác.
- Một địa chỉ email dùng làm tên đăng nhập có thể thay đổi theo quy trình nghiệp vụ; nó không đương nhiên là định danh ổn định suốt đời của tài khoản.
- Một thực thể chưa có mã được cấp chính thức cần chính sách nhận diện trước khi tham gia Set theo mã ấy. Không đưa nhiều đối tượng “chưa có id” vào cùng một quy tắc bằng nhau mơ hồ, rồi hy vọng Set sẽ tự điều chỉnh khi id được cấp.

Một khóa giá trị đơn giản có thể được biểu diễn bằng record:

```java
// Trích đoạn khai báo; có thể đặt trong một lớp phù hợp.
record CustomerKey(long id) {
}
```

`long` là giá trị nguyên thủy; `id` của record không có setter. Nếu định danh đã được xác lập đúng và không phải đổi, kiểu này giúp biểu diễn ý định rõ hơn một đối tượng lớn có nhiều dữ liệu mô tả.

Với khóa gồm `String`, bản thân `String` là bất biến; nhưng vẫn phải quyết định chính sách nghiệp vụ: có phân biệt chữ hoa–thường không, có chuẩn hóa khoảng trắng không, có cho phép giá trị trống không. Chuẩn hóa khi tạo khóa giúp mọi nơi dùng cùng một giá trị chuẩn. Không gọi chuẩn hóa có tác dụng phụ từ bên trong `equals`.

## 9. Chương trình 3: dữ liệu mô tả có thể đổi khi định danh ổn định

Ví dụ sau chọn `id` đã được cấp làm định danh của `Customer`. Tên hiển thị không tham gia so sánh hoặc băm.

Lưu tệp `StableIdentitySetDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class StableIdentitySetDemo {
    static final class Customer {
        private final long id;
        private String displayName;

        Customer(long id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        void rename(String newName) {
            displayName = newName;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Customer customer && id == customer.id);
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Customer original = new Customer(7L, "Lan");
        Set<Customer> customers = new HashSet<>();
        customers.add(original);
        int hashBefore = original.hashCode();

        original.rename("Minh");
        Customer probe = new Customer(7L, "Another name");

        System.out.println("hash unchanged after rename = "
                + (hashBefore == original.hashCode()));
        System.out.println("contains original = " + customers.contains(original));
        System.out.println("contains equal probe = " + customers.contains(probe));
        System.out.println("add equal probe = " + customers.add(probe));
        System.out.println("size = " + customers.size());
        System.out.println("stored reference is original = "
                + (customers.iterator().next() == original));
        System.out.println("stored name = "
                + customers.iterator().next().displayName);
        System.out.println("remove equal probe = " + customers.remove(probe));
        System.out.println("empty after remove = " + customers.isEmpty());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 StableIdentitySetDemo.java
java StableIdentitySetDemo
```

Kết quả của lần chạy kiểm chứng:

```text
hash unchanged after rename = true
contains original = true
contains equal probe = true
add equal probe = false
size = 1
stored reference is original = true
stored name = Minh
remove equal probe = true
empty after remove = true
```

Đổi tên từ `Lan` sang `Minh` không thay đổi việc khách hàng mang `id = 7` là ai. Đối tượng thăm dò có tên khác vẫn được Set nhận diện là cùng một thành viên.

Lời gọi `add(probe)` trả về `false` và không thay thế đối tượng đã lưu. Sau đó, Set vẫn giữ tham chiếu `original` cùng tên `Minh`. Đây là điều cần nhớ khi dùng Set để “cập nhật bản ghi”: thêm một đối tượng bằng nhau không đồng nghĩa với cập nhật dữ liệu của đối tượng cũ.

Ví dụ chọn lớp `final` để không mở thêm vấn đề đối xứng khi lớp con thay đổi quy tắc bằng nhau. Trong một thiết kế có kế thừa, cần xem xét hợp đồng giữa lớp cha và lớp con, thay vì sao chép `instanceof` một cách máy móc.

Thiết kế này chỉ phù hợp khi:

- `id` thực sự ổn định trong vòng đời cần quản lý.
- Hai đối tượng cùng `id` phải được xem là cùng khách hàng trong phạm vi ứng dụng.
- Tên hiển thị không phải một phần của giá trị dùng để phân biệt thành viên.

Nếu yêu cầu nghiệp vụ là lưu nhiều phiên bản tên của cùng khách hàng dưới các thời điểm khác nhau, cần một khóa phiên bản phù hợp. Không giữ nguyên `equals` theo `id` rồi mong Set chứa mọi phiên bản.

Một lựa chọn khác là tách khóa khỏi dữ liệu có thể sửa:

```java
// Trích đoạn mô hình, không phải chương trình độc lập.
record CustomerKey(long id) {
}

final class CustomerProfile {
    private String displayName;

    CustomerProfile(String displayName) {
        this.displayName = displayName;
    }

    void rename(String newName) {
        displayName = newName;
    }
}

// Khi cần cả tra cứu theo khóa lẫn cập nhật dữ liệu mô tả:
// Map<CustomerKey, CustomerProfile> profiles = new HashMap<>();
```

Đây là cách thể hiện rằng định danh và nội dung được cập nhật có trách nhiệm khác nhau. Tuy nhiên, chọn Map còn tùy thao tác của bài toán; không cần thay mọi Set bằng Map chỉ vì phần tử có một trường mô tả.

## 10. final và record chỉ giúp đúng trong phạm vi chúng bảo vệ

Một trường `final` kiểu tham chiếu ngăn thay chính tham chiếu sau khởi tạo; nó không ngăn sửa đối tượng được tham chiếu.

Ví dụ:

```java
// Trích đoạn minh họa.
final List<String> tags = new ArrayList<>();
tags.add("A");   // Hợp lệ: thay nội dung List.
tags.add("B");   // Vẫn hợp lệ.
```

Record cũng không tự đóng băng toàn bộ cây đối tượng. [Tài liệu Record Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) mô tả record là bất biến nông: các thành phần được cố định theo tham chiếu hoặc giá trị trực tiếp, nhưng đối tượng nằm sau một tham chiếu có thể vẫn khả biến.

Nếu record chứa `List<String>`, phương thức bằng nhau và mã băm được sinh mặc định sẽ phụ thuộc vào giá trị thành phần List. Thay đổi nội dung của List có thể làm thay đổi nhận diện của record.

### 10.1. Chương trình 4: bản sao bảo vệ cho thành phần List

`UnsafeKey` nhận thẳng List do bên ngoài giữ. `SafeKey` dùng hàm khởi tạo rút gọn (compact constructor) để nhận một bản chụp không cho sửa qua List đó.

Lưu tệp `RecordKeySnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordKeySnapshotDemo {
    record UnsafeKey(List<String> tags) {
    }

    record SafeKey(List<String> tags) {
        SafeKey {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("A"));
        UnsafeKey unsafe = new UnsafeKey(input);
        SafeKey safe = new SafeKey(input);
        Set<UnsafeKey> unsafeSet = new HashSet<>();
        Set<SafeKey> safeSet = new HashSet<>();
        unsafeSet.add(unsafe);
        safeSet.add(safe);

        System.out.println("unsafe contains before change = "
                + unsafeSet.contains(unsafe));
        input.add("B");

        System.out.println("input size = " + input.size());
        System.out.println("unsafe tags size = " + unsafe.tags().size());
        System.out.println("safe tags size = " + safe.tags().size());
        System.out.println("unsafe contains after change = "
                + unsafeSet.contains(unsafe));
        System.out.println("safe contains original = " + safeSet.contains(safe));
        System.out.println("safe contains equal snapshot = "
                + safeSet.contains(new SafeKey(List.of("A"))));

        try {
            safe.tags().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutate safe tags = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 RecordKeySnapshotDemo.java
java RecordKeySnapshotDemo
```

Kết quả của lần chạy kiểm chứng:

```text
unsafe contains before change = true
input size = 2
unsafe tags size = 2
safe tags size = 1
unsafe contains after change = false
safe contains original = true
safe contains equal snapshot = true
mutate safe tags = UnsupportedOperationException
```

Phần `unsafeSet` là thí nghiệm cố ý thay đổi dữ liệu dùng nhận diện sau khi thêm phần tử; các kết quả sau thay đổi là quan sát trên triển khai đã kiểm chứng. Phần `safeSet` giữ khóa ổn định trong ví dụ này.

### 10.2. Sao chép cái gì, bảo vệ được tới đâu?

Trong constructor:

```java
SafeKey {
    tags = List.copyOf(tags);
}
```

Tham số `tags` được thay bằng kết quả `List.copyOf` trước khi được gán cho thành phần của record. Theo [List.copyOf trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), List trả về không cho sửa cấu trúc, không phản ánh sửa đổi tiếp theo của collection đầu vào, và không chấp nhận đầu vào hoặc phần tử `null`.

Trong ví dụ, phần tử là `String` bất biến, nên không còn đường sửa nội dung nhận diện qua các chuỗi ấy. Nếu thành phần là `List<MutableTag>`, chỉ sao chép List chưa đủ: đối tượng `MutableTag` vẫn có thể bị sửa qua tham chiếu được chia sẻ.

Khi đó, cần một trong những lựa chọn có chủ đích:

- Chuyển từng phần tử thành một giá trị bất biến dùng làm khóa.
- Sao chép phòng vệ đủ sâu đối với những phần tham gia nhận diện.
- Chỉ dùng một định danh bất biến của phần tử lồng bên trong.
- Đổi mô hình để phần dữ liệu lồng có thể sửa không tham gia khóa.

Không cần sao chép sâu toàn bộ đồ thị đối tượng nếu dữ liệu không liên quan đến nhận diện. Nhưng phải biết chính xác đường tham chiếu nào có thể làm đổi `equals` hoặc `hashCode`.

### 10.3. Các đường sửa gián tiếp dễ bị bỏ sót

Khóa có thể đổi mà không có setter trực tiếp trên lớp khóa:

- Constructor giữ lại mảng hoặc List đầu vào mà bên gọi vẫn sở hữu.
- Getter trả thẳng collection nội bộ.
- Một đối tượng lồng trong khóa có setter.
- Một collection làm khóa được thêm, xóa hoặc thay phần tử.
- Mã gọi giữ một tham chiếu khác tới cùng đối tượng, rồi sửa qua tham chiếu đó.

Vì vậy, kiểm tra “lớp không có setter” mới là bước đầu. Cần kiểm tra cả dữ liệu đầu vào, dữ liệu đầu ra và thành phần lồng trong khóa.

Với mảng, còn phải quyết định ngữ nghĩa bằng nhau theo tham chiếu hay theo nội dung. Đừng giả định rằng mọi thành phần tham chiếu của record đều tự được so sánh sâu theo cách mong muốn. Hãy chọn một kiểu khóa biểu đạt rõ ngữ nghĩa, thay vì chỉ chọn cú pháp ngắn.

## 11. Nếu nghiệp vụ thật sự cần đổi khóa thì làm thế nào?

### 11.1. Ưu tiên tạo khóa mới

Với khóa giá trị bất biến, “đổi mã” thường nên được hiểu là gỡ giá trị cũ và đưa giá trị mới vào:

```java
// Trích đoạn trong luồng xử lý đơn luồng, Set ban đầu hợp lệ.
record CodeKey(int code) {
}

Set<CodeKey> keys = new HashSet<>();
CodeKey oldKey = new CodeKey(1);
CodeKey replacement = new CodeKey(2);
keys.add(oldKey);

if (keys.contains(replacement)) {
    throw new IllegalStateException("Replacement key already exists");
}
if (!keys.remove(oldKey)) {
    throw new IllegalStateException("Old key is missing");
}
if (!keys.add(replacement)) {
    throw new IllegalStateException("Replacement was not added");
}
```

Đây là đoạn minh họa thứ tự thao tác, không phải một giao dịch tổng quát. Nó giả định không có luồng khác chen vào, không có tác dụng phụ trong `equals`–`hashCode`, và không có lỗi giữa các bước. Các kiểu cần thiết như `Set`, `HashSet` được import trong chương trình bao quanh.

Kiểm tra xung đột trước giúp tránh gỡ khóa cũ rồi mới phát hiện khóa mới đã được dùng. Trong ứng dụng có nhiều cấu trúc liên quan, việc đổi định danh cần một quy trình nghiệp vụ thống nhất, có chính sách thất bại phù hợp.

Tạo khóa mới không làm thay đổi khóa cũ mà một cấu trúc khác đang giữ. Đây là ưu điểm lớn so với sửa tại chỗ cùng một đối tượng được chia sẻ rộng rãi.

### 11.2. Nếu bắt buộc giữ đối tượng khả biến

Thứ tự tối thiểu trong một tình huống đã kiểm soát là:

```text
1. Khi khóa cũ còn nguyên, xác định xung đột với giá trị mới.
2. Gỡ phần tử khỏi mọi chỉ mục phụ thuộc vào khóa sắp đổi.
3. Kiểm tra thao tác gỡ đã thành công.
4. Thay đổi dữ liệu nhận diện.
5. Thêm lại vào các chỉ mục theo khóa mới.
6. Xử lý lỗi và xung đột theo chính sách đã thiết kế.
```

Điều kiện “khóa cũ còn nguyên” là thiết yếu. Nếu đã sửa trước rồi mới gọi `remove`, chương trình đã rơi vào chính tình huống mất dấu đang học.

Một đối tượng có thể đồng thời là:

- Phần tử trong `HashSet`.
- Khóa trong `HashMap`.
- Thành phần của một khóa tổng hợp ở nơi khác.
- Phần tử trong một cấu trúc sắp xếp theo thuộc tính ấy.

Gỡ khỏi một Set không sửa được các chỉ mục khác. Khi có nhiều nơi giữ tham chiếu, việc bảo đảm quy trình trở nên khó hơn; đó là lý do khóa bất biến thường giảm đáng kể gánh nặng kiểm soát.

### 11.3. Đừng bỏ qua xung đột

Giả sử đã có khách hàng mã `2`, và một khách hàng mã `1` được đổi thành `2`. Sau khi gỡ khách hàng cũ, `add` theo khóa mới có thể trả về `false` vì thành viên tương đương đã tồn tại.

Set không thể quyết định nên hợp nhất, từ chối, ghi đè, hay giữ một lịch sử phiên bản. Đó là chính sách nghiệp vụ. Bỏ qua giá trị trả về của `add` dễ biến một lỗi định danh thành mất dữ liệu trong luồng xử lý.

Đối với hệ thống có nhiều luồng, chuỗi `contains` → `remove` → `add` cũng không tự trở thành nguyên tử chỉ vì cấu trúc có hỗ trợ đồng thời ở từng thao tác. Phải thiết kế cơ chế phối hợp cho toàn bộ yêu cầu cập nhật.

## 12. Chẩn đoán một Set đã có dấu hiệu mất dấu

Một dấu hiệu đáng điều tra là: duyệt thấy đối tượng nhưng `contains` bằng chính đối tượng ấy lại trả về `false`. Hãy bắt đầu từ dữ liệu và đường sửa của khóa.

### 12.1. Thu thập thông tin có ý nghĩa

Ở ranh giới thêm phần tử, có thể ghi nhận phục vụ điều tra:

- Giá trị định danh lúc thêm.
- Giá trị định danh hiện tại.
- Mã băm lúc thêm và hiện tại, nếu đã có ghi nhận.
- Thời điểm và nơi thực hiện thao tác thay đổi.
- Những cấu trúc khác đang giữ cùng đối tượng.

Không thể lấy lại “mã băm lúc thêm” bằng cách gọi `hashCode` sau khi đối tượng đã đổi. Lời gọi mới đọc trạng thái hiện tại; nó không cung cấp lịch sử.

Cũng không chỉ nhìn `toString`: phương thức đó có thể không in trường định danh, hoặc cũng đọc giá trị mới. Cần quan sát đúng dữ liệu mà `equals`–`hashCode` thực sự sử dụng.

### 12.2. Kiểm tra đường sửa, kể cả gián tiếp

Tìm các setter, thao tác cập nhật collection lồng bên trong, constructor giữ lại dữ liệu đầu vào và getter làm lộ đối tượng có thể sửa. Kiểm tra cả mã ánh xạ dữ liệu hoặc gán định danh sau khi đã thêm vào Set.

Một đối tượng có mã băm không đổi chưa đủ để kết luận an toàn: hai đối tượng vốn không bằng nhau có thể đã trở thành bằng nhau sau thay đổi dữ liệu. Cần so cả ngữ nghĩa nhận diện, không chỉ con số hash.

### 12.3. Tạm dừng thay đổi trước khi phục hồi

Nếu dữ liệu vẫn tiếp tục đổi trong lúc kiểm tra, một lần dựng lại Set có thể lập tức sai trở lại. Trước hết phải chặn hoặc sửa đường tạo lỗi.

Không đưa ra một phép chữa chung như:

```java
// Cách vá thiếu cơ sở: không dùng làm quy trình phục hồi.
keys.add(lostKey);
```

Ví dụ đầu đã cho thấy thêm lại có thể tạo thêm một mục cho cùng tham chiếu.

Tương tự, không mặc định rằng tăng dung lượng, ép Set phát triển, bọc bằng một wrapper khác hoặc gọi lại `contains` nhiều lần sẽ phục hồi chỉ mục. Những việc ấy không xác lập lại một mô hình khóa hợp lệ.

### 12.4. Dựng lại có kiểm soát và giải quyết trùng lặp

Khi đã biết dữ liệu chuẩn hiện tại và đã dừng thay đổi định danh, một hướng phục hồi là đọc dữ liệu cần giữ, chuyển thành khóa ổn định, rồi dựng một cấu trúc mới.

Nhưng trước khi loại trùng, phải xác định chính sách. Hai mục hiện tại cùng một khóa có thể chứa hai hồ sơ khác nhau hoặc hai lịch sử cập nhật. Dựng một `HashSet` mới có thể làm một trong các giá trị tương đương không được thêm; việc đó chưa phải quyết định nghiệp vụ hợp lệ.

Một quy trình điều tra cẩn thận thường gồm:

1. Lưu dấu vết các mục đang có để có thể đối chiếu.
2. Xác định khóa chuẩn hiện tại của từng mục.
3. Nhóm các mục xung đột theo khóa chuẩn.
4. Quyết định giữ, hợp nhất hoặc từ chối theo nghiệp vụ.
5. Tạo khóa ổn định và dựng lại chỉ mục.
6. Chỉ chuyển sang chỉ mục mới khi kiểm tra hoàn tất.

Với một Set đã bị dùng ngoài điều kiện đặc tả, không xem hành vi của mọi phép tìm hoặc xóa là nền tảng chắc chắn để sửa tự động. Cần dựa trên dữ liệu chuẩn và quy trình do ứng dụng kiểm soát.

Dựng một Set mới từ các tham chiếu cũ cũng không tự làm cho phần tử bất biến. Nếu vẫn chia sẻ các đối tượng có thể đổi khóa, lỗi có thể tái diễn.

## 13. Đổi loại collection hoặc bọc chỉ đọc có giải quyết được không?

| Cách thay đổi | Điều nó có thể cung cấp | Điều vẫn phải giữ đúng |
|---|---|---|
| `HashSet` sang `LinkedHashSet` | Thứ tự gặp phần tử theo quy tắc của cấu trúc | Khóa dùng băm và bằng nhau vẫn phải ổn định |
| Chuyển sang `TreeSet` | Tính duy nhất và thứ tự theo so sánh | Dữ liệu dùng so sánh phải ổn định; không phải cách chữa khóa tùy ý đổi |
| Set dựa trên cấu trúc đồng thời | Khả năng phối hợp các thao tác theo hợp đồng riêng | Không tự theo dõi setter hoặc tái lập định danh cho phần tử |
| Wrapper không cho sửa Set | Hạn chế thêm hoặc gỡ qua wrapper | Không tự đóng băng các đối tượng nằm bên trong |
| Sao chép Set | Tạo một cấu trúc chứa khác | Không đương nhiên sao chép hoặc làm bất biến phần tử |
| `final Set<Key> keys` | Không gán biến `keys` sang Set khác | Không ngăn sửa Set hoặc sửa từng Key |

Bảng này là cách suy luận thiết kế, không phải yêu cầu rằng mọi cấu trúc đều có cùng chi tiết nội bộ. Khi đổi loại collection, phải đọc hợp đồng riêng của nó. Một cây sắp xếp và một bảng băm có cơ chế khác nhau, nhưng đều cần dữ liệu dùng lập chỉ mục đáp ứng điều kiện sử dụng.

Chỉ đọc ở cấp container và bất biến ở cấp phần tử là hai mức bảo vệ khác nhau. Ví dụ, không cho gọi `add` không có nghĩa không ai còn tham chiếu để gọi `customer.rename` hoặc sửa một List trong khóa.

Tài liệu [Set Java 17 về các Set không cho sửa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable) cũng lưu ý rằng thành phần khả biến có thể làm Set hoạt động không nhất quán hoặc làm nội dung có vẻ thay đổi. Vì vậy, `Set.copyOf` không phải công cụ “đóng băng sâu” mọi đối tượng.

Đối với lập trình nhiều luồng, có hai câu hỏi riêng: các thao tác trên cấu trúc có được phối hợp đúng không, và định danh của phần tử có ổn định không. Giải quyết câu hỏi thứ nhất không tự giải quyết câu hỏi thứ hai.

## 14. Kiểm tra theo hợp đồng và theo vòng đời

Bộ kiểm tra tốt nên dùng đối tượng đại diện cho quy tắc nghiệp vụ, thay vì chỉ xác nhận một output thuận mắt của HashSet.

### 14.1. Kiểm tra hai phương thức cùng nhau

Với các đối tượng `a`, `b`, `c` được dự kiến là cùng một định danh, hãy kiểm tra:

- Phản xạ: `a.equals(a)`.
- Đối xứng: kết quả của `a.equals(b)` và `b.equals(a)` thống nhất.
- Bắc cầu khi các quan hệ đầu vào tương ứng đúng.
- So với `null` trả về `false`.
- Khi `a.equals(b)`, hai mã băm bằng nhau.
- Khi dữ liệu nhận diện không đổi, gọi lại mã băm không đổi trong cùng lần chạy.

Không viết kiểm tra bắt buộc hai đối tượng không bằng nhau phải có mã băm khác nhau. Một kiểm tra như vậy từ chối cả những va chạm hợp lệ.

### 14.2. Kiểm tra hành vi thành viên

Với thiết kế khóa hợp lệ, thêm `a` rồi kiểm tra bằng một đối tượng `b` khác tham chiếu nhưng cùng định danh:

```text
add(a)             -> true
contains(b)        -> true
add(b)             -> false
size()             -> 1
remove(b)          -> true
isEmpty()          -> true
```

Đây là kịch bản mong đợi cho trường hợp đơn giản bắt đầu từ Set rỗng, với hai phần tử hợp lệ bằng nhau và không có thay đổi xen vào. Nó không yêu cầu một giá trị hash cụ thể.

### 14.3. Kiểm tra thuộc tính được phép cập nhật

Nếu thiết kế cho phép đổi `displayName` mà không đổi `id`, hãy kiểm tra sau đổi tên:

- Mã băm vẫn giữ nguyên.
- Đối tượng thăm dò theo cùng `id` vẫn bằng nhau.
- `contains` và `remove` vẫn hoạt động theo cùng định danh.
- Thêm một đối tượng cùng `id` không tạo thêm thành viên.

Đây là bài kiểm tra vòng đời như chương trình 3. Nó bảo vệ trực tiếp quyết định rằng tên không phải định danh.

### 14.4. Kiểm tra sự chia sẻ dữ liệu trong khóa

Với một khóa nhận vào collection, thử thay đổi collection gốc sau khi tạo khóa. Nếu mục tiêu là bản chụp, giá trị khóa không được đổi theo đầu vào.

Cũng thử sửa qua getter. Nếu getter trả ra cấu trúc có thể sửa nội dung nhận diện, constructor sao chép một lần có thể vẫn chưa bảo vệ đủ.

Với collection chứa đối tượng khả biến, kiểm tra thêm việc sửa thành phần lồng bên trong. Một bài kiểm tra chỉ thêm phần tử vào List gốc sẽ chưa phát hiện đường sửa qua một đối tượng con.

### 14.5. Kiểm tra luồng đổi định danh và xung đột

Khi nghiệp vụ có đổi mã, ít nhất cần các tình huống:

- Khóa mới chưa có.
- Khóa mới đã có một thành viên khác.
- Khóa cũ không còn ở trong cấu trúc.
- Lỗi phát sinh giữa các bước nếu luồng cập nhật có thể ném lỗi.
- Một đối tượng được lập chỉ mục ở nhiều nơi.
- Các yêu cầu cập nhật có thể chạy đồng thời.

Không viết bài kiểm tra yêu cầu “sửa khóa trong Set thì contains phải false”. Đó là biểu hiện có thể quan sát của một cách sử dụng sai, không phải hành vi đúng mà ứng dụng nên phụ thuộc.

## 15. Những lỗi đọc hiểu và triển khai thường gặp

| Nhận định hoặc cách làm | Vấn đề | Cách suy nghĩ phù hợp |
|---|---|---|
| “Set không cho trùng nên không thể có trạng thái sai” | Bỏ qua điều kiện đối với phần tử và quy tắc bằng nhau | Kiểm tra hợp đồng lớp và vòng đời khóa |
| Chỉ override `equals` khi cần bằng nhau theo giá trị | Cách băm có thể không còn phù hợp | Thiết kế hai phương thức như một cặp |
| `equals` theo `id`, hash theo cả tên | Hai đối tượng cùng id có thể bị băm khác | Chọn thông tin băm nhất quán với bằng nhau |
| Đưa mọi trường vào equals/hash bằng công cụ sinh mã | Trường mô tả hay collection khả biến có thể thành định danh ngoài ý muốn | Chọn ngữ nghĩa trước khi sinh mã |
| Thấy `final` nên cho rằng dữ liệu bất biến | Chỉ cố định tham chiếu ở mức trực tiếp | Kiểm tra đối tượng được tham chiếu |
| Thấy `record` nên bỏ qua List hoặc đối tượng lồng | Record không tự sao chép sâu | Chụp và bảo vệ thành phần nhận diện |
| Gọi setter khóa rồi mới remove | Tra cứu xóa dùng khóa mới | Gỡ khi khóa cũ còn hợp lệ hoặc dùng giá trị mới bất biến |
| Add lại phần tử bị mất dấu | Có thể tạo thêm mục cho cùng đối tượng | Chẩn đoán và phục hồi có kiểm soát |
| Giữ hash hằng để “không mất ngăn” | Quan hệ bằng nhau vẫn có thể đổi; phân bố cũng kém | Giữ ổn định định danh, không chỉ con số hash |
| Bỏ qua kết quả `add` khi cập nhật | Không biết khóa mới đã có | Thiết kế chính sách xung đột |
| Dùng Set chỉ đọc để bảo vệ khóa | Đối tượng bên trong vẫn có thể bị sửa | Bảo vệ ở cấp dữ liệu nhận diện |
| Cho rằng không có ngoại lệ là sử dụng đúng | Một lỗi ngữ nghĩa có thể diễn ra bình thường | Kiểm tra các bất biến của mô hình |

Một thói quen hữu ích là đọc mọi trường tham gia `equals` và đặt câu hỏi: “Ai có thể thay đổi dữ liệu này, qua những tham chiếu nào, vào thời điểm nào?” Nếu câu trả lời vượt ra ngoài ranh giới kiểm soát của Set, nên cân nhắc tách khóa bất biến.

Không chỉ rà setter trong chính lớp. Một mảng, List hoặc đối tượng con được chia sẻ thường là nguồn lỗi khó thấy hơn một phương thức tên rõ ràng như `setId`.

## 16. Bài tập áp dụng

### Bài 1: khách hàng đổi tên

Một lớp có `id` bất biến và `displayName` khả biến. `equals` theo `id`; `hashCode` theo cả `id` và `displayName`.

Hãy chỉ ra lỗi trước khi chạy Set.

**Gợi ý trả lời:** hai đối tượng cùng `id` nhưng khác tên được `equals` xem là bằng nhau, trong khi công thức hash có thể cho kết quả khác. Đây là lỗi hợp đồng, không cần chờ một đối tượng được sửa sau khi thêm.

### Bài 2: tọa độ thay đổi

Một điểm có `x`, `y` khả biến; cả hai phương thức dựa vào `x`, `y`. Chương trình thêm điểm vào HashSet, rồi tăng `x`.

Hãy giải thích vì sao lớp có thể so sánh hợp lý tại từng thời điểm mà luồng sử dụng Set vẫn sai.

**Gợi ý trả lời:** quy tắc nhận diện giá trị đã đổi trong thời gian phần tử nằm trong Set. Nên dùng điểm bất biến và tạo một điểm mới, hoặc quản lý việc gỡ và thêm lại trước–sau thay đổi trong một luồng được kiểm soát.

### Bài 3: hash luôn bằng 0

Hai phần tử ban đầu khác nhau được thêm vào Set. Sau đó một phần tử được sửa để bằng phần tử kia. Hash của cả hai luôn bằng `0`.

Việc hash không đổi có làm quá trình này hợp lệ không?

**Gợi ý trả lời:** không. Điều kiện liên quan đến quan hệ bằng nhau đã bị phá vỡ. Set không tự hợp nhất hai mục khi setter làm chúng trở thành bằng nhau.

### Bài 4: record chứa List

Tạo `record SearchKey(List<String> filters)`. Constructor nhận một `ArrayList`, rồi bên gọi thêm bộ lọc vào List ấy sau khi SearchKey đã nằm trong Set.

Hãy thiết kế một phiên bản dùng bản chụp và nêu giới hạn.

**Gợi ý trả lời:** sao chép bằng `List.copyOf` trong hàm khởi tạo rút gọn có thể phù hợp nếu muốn cấm `null` và thành phần là chuỗi bất biến. Nếu thành phần lồng bên trong khả biến, phải bảo vệ thêm dữ liệu tham gia nhận diện.

### Bài 5: id được cấp sau

Đối tượng được tạo chưa có mã chính thức, được đưa vào Set theo mã đó, rồi mới nhận mã sau khi lưu dữ liệu.

Hãy đề xuất ranh giới vòng đời hợp lý.

**Gợi ý trả lời:** xác lập định danh ổn định trước khi tham gia Set theo định danh ấy, hoặc dùng một khóa ổn định khác có ngữ nghĩa rõ. Không mặc định mã “chưa có” và mã đã cấp là hai trạng thái mà cùng một chỉ mục sẽ tự cập nhật.

### Bài 6: Set có size bằng 1 nhưng contains bằng false

Hãy mô tả dữ liệu cần thu thập và một hành động không nên làm.

**Gợi ý trả lời:** đối chiếu định danh lúc thêm và hiện tại, kiểm tra đường sửa trực tiếp hoặc gián tiếp, xem nơi khác cùng giữ tham chiếu. Không add lại ngay để “chắc chắn đã có”; trước hết phải ngăn đường làm đổi khóa và xác định trạng thái chuẩn.

### Bài 7: đổi khóa sang một giá trị đã tồn tại

Một Set quản lý khách hàng theo mã. Muốn đổi mã của A thành mã hiện có của B.

Hãy nêu quyết định mà Set không thể tự đưa ra.

**Gợi ý trả lời:** giữ A, giữ B, hợp nhất, từ chối hay lưu phiên bản là chính sách nghiệp vụ. Luồng cập nhật phải kiểm tra và xử lý xung đột; việc `add` trả về `false` không tự tạo ra một kết quả cập nhật đúng.

Khi tự thiết kế một khóa mới, hãy viết rõ ba điều ngay trong quyết định thiết kế: dữ liệu nào định nghĩa bằng nhau, dữ liệu ấy có thể đổi bằng những đường nào, và thời điểm nào đối tượng được phép tham gia hoặc rời khỏi các cấu trúc lập chỉ mục.
