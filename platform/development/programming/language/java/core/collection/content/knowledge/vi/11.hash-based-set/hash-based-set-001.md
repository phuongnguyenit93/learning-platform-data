# HashSet và quan hệ với bảng băm

Một `HashSet` trả lời câu hỏi “phần tử này có thuộc tập hợp không?” và bảo đảm không lưu nhiều thành viên tương đương. Để không phải quét lần lượt mọi phần tử cho mỗi lần tìm, nó dùng một bảng băm để thu hẹp nơi cần tìm.

Trong Java, quan hệ còn cụ thể hơn: `HashSet` được hậu thuẫn bởi một `HashMap`. Phần tử của set được đặt làm **khóa** của map; giá trị đi kèm chỉ đóng vai trò đánh dấu có mặt.

Hiểu mối quan hệ này giúp giải thích các hành vi của `add`, `contains`, `remove`, việc cho phép `null`, xử lý va chạm, tăng bảng và giới hạn của kết luận O(1). Các ví dụ dùng Java 17 trở lên; chi tiết thuật toán nội bộ được gắn với bản OpenJDK 17 cụ thể khi cần.

## 1. Set là yêu cầu về dữ liệu, bảng băm là cách thực hiện

Một set mô tả các thành viên duy nhất. Nếu đã có A, thêm A nữa không tạo thêm một thành viên A thứ hai.

Một bảng băm là cấu trúc lưu trữ và tìm kiếm dựa trên mã băm của khóa. Nó không tự mang ý nghĩa “tập hợp” hay “từ điển”; ý nghĩa đó phụ thuộc cách cấu trúc được sử dụng.

Có thể nhìn các lớp theo ba tầng:

~~~text
Set<E>
  hop dong: khong co thanh vien trung

HashSet<E>
  mot cach thuc hien hop dong Set

HashMap<E, gia tri danh dau>
  co che bang bam giup quan ly cac khoa duy nhat
~~~

Ở đây, “bảng băm” là thuật ngữ cấu trúc dữ liệu. Nó không có nghĩa là `HashSet` dùng lớp Java tên `Hashtable`. [Tài liệu HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) nêu rõ map hậu thuẫn là `HashMap`.

### 1.1. Vì sao không chỉ giữ một danh sách?

Nếu lưu các phần tử trong một danh sách thông thường, để kiểm tra phần tử mới đã tồn tại chưa có thể phải so sánh với nhiều phần tử trước đó.

Bảng băm dùng một phép tính nhanh để chọn một vùng ứng viên nhỏ hơn. Sau đó, nó vẫn phải kiểm tra khóa phù hợp; mã băm không thay thế hoàn toàn việc xác định bằng nhau.

Đổi lại, cấu trúc cần bộ nhớ cho bảng, các mục lưu khóa và thông tin quản lý. Lợi ích tìm kiếm không phải miễn phí, và phụ thuộc chất lượng phân bố mã băm.

### 1.2. HashSet không cần một giá trị nghiệp vụ cho mỗi phần tử

Một `HashMap<CustomerId, Customer>` lưu ánh xạ từ mã đến dữ liệu khách hàng. Một `HashSet<CustomerId>` chỉ cần ghi nhận mã nào có mặt.

Vì thế, set có thể dùng map mà bỏ ý nghĩa nghiệp vụ của phần giá trị. Mọi khóa được ánh xạ tới cùng một giá trị đánh dấu khác `null`.

Cách dùng này tận dụng việc `HashMap` vốn đã quản lý khóa duy nhất. Không cần phát minh lại một bộ xử lý băm chỉ để xây một tập hợp.

## 2. Phần tử của HashSet nằm ở phía khóa của HashMap

Giả sử set có các thành viên java và spring. Có thể mô hình hóa map hậu thuẫn như sau:

~~~text
HashSet: {java, spring}

HashMap hau thuan:
key       value
java      PRESENT
spring    PRESENT
~~~

`PRESENT` biểu diễn một đối tượng đánh dấu. Nó không phải dữ liệu mà người dùng của `HashSet` cần truy cập.

Trong [mã nguồn HashSet OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java), map chứa khóa kiểu E và một giá trị đánh dấu dùng chung.

### 2.1. Bảng đối chiếu thao tác

| Thao tác trên set | Việc tương ứng trên map hậu thuẫn |
|---|---|
| Thêm phần tử e | Đưa e vào phía khóa, gắn giá trị đánh dấu |
| Kiểm tra có e | Kiểm tra có khóa e |
| Xóa e | Xóa ánh xạ có khóa e |
| Số thành viên | Số ánh xạ trong map |
| Duyệt phần tử | Duyệt các khóa |
| Xóa toàn bộ | Xóa các ánh xạ |

Một phần tử không phải được lưu ở phía value để tìm bằng `containsValue`. Tính duy nhất đến từ các khóa.

### 2.2. Vì sao add biết lần này có mới không?

`HashMap.put` trả về giá trị cũ gắn với khóa, hoặc `null` khi không có ánh xạ trước đó. Trong map nội bộ của `HashSet`, mọi ánh xạ hiện có đều có giá trị đánh dấu khác `null`.

Do đó:

~~~text
put khoa moi:
  khong co gia tri cu -> tra null
  HashSet.add -> true

put khoa da co:
  gia tri cu la dau PRESENT
  HashSet.add -> false
~~~

Không cần một lần tìm toàn set riêng để xác định kết quả sau khi thêm. Bước đưa vào map đã biết khóa có tồn tại hay chưa.

Trong chương trình học tập bên dưới, `Boolean.TRUE` được dùng làm dấu để minh họa. Nó không phải mô tả rằng `HashSet` thật lưu giá trị Boolean; triển khai được tham chiếu dùng đối tượng đánh dấu riêng.

### 2.3. Tại sao phải nhấn mạnh giá trị đánh dấu khác null?

Với một `HashMap` tổng quát, map có thể có một khóa đang được ánh xạ tới giá trị `null`. Khi put khóa đó, giá trị trả về cũ vẫn là `null`, dù khóa đã có mặt.

Bởi vậy, quy tắc:

~~~text
put(...) tra null -> chac chan khoa truoc do chua ton tai
~~~

không đúng cho mọi cách dùng `HashMap`.

Nó dùng được để nhận diện thêm mới trong mô hình của set vì có điều kiện bổ sung: mọi thành viên hiện có luôn mang một dấu khác `null`.

Nếu tự xây một cấu trúc dựa trên map, phải bảo toàn điều kiện của mô hình. Đừng lấy một biểu thức đúng trong map nội bộ có kiểm soát rồi áp dụng cho một map cho phép mọi giá trị tùy ý.

### 2.4. Map hậu thuẫn là chi tiết nội bộ

Người dùng không nhận được map nội bộ để tự thay giá trị hoặc thêm/xóa khóa theo đường riêng. API `HashSet` cung cấp các thao tác set.

Mối quan hệ này giải thích cơ chế, không phải lời mời ép kiểu `HashSet` thành `HashMap`, hay dùng reflection vào trường riêng để viết mã ứng dụng. `HashSet` cũng không kế thừa `HashMap`; nó sử dụng map như một thành phần bên trong.

## 3. Bảng băm tổ chức việc tìm khóa như thế nào?

Một mô hình phổ biến của bảng băm gồm:

- Một mảng các **bucket** — các ngăn chứa theo chỉ số.
- Mã băm của mỗi khóa.
- Các mục lưu khóa và thông tin liên kết trong bucket.
- Cách kiểm tra bằng nhau khi có nhiều khóa cùng vùng.

Quá trình khái quát:

~~~text
phan tu / khoa
      |
      v
hashCode cua khoa
      |
      v
xu ly ma bam, tinh chi so bucket
      |
      v
chon bucket ung vien
      |
      v
kiem tra khoa phu hop trong bucket
      |
      v
ket luan co / khong co
~~~

Mục tiêu là không phải xét mọi bucket và mọi phần tử cho một lần `contains`.

### 3.1. Mã băm không phải chỉ số danh sách

`hashCode()` trả một số nguyên `int`, có thể âm. Nó không trực tiếp là một vị trí từ 0 đến size−1.

Bảng cần biến mã băm thành chỉ số nằm trong số bucket hiện có. Kích thước bảng là một thông tin của cấu trúc, tách khỏi số phần tử.

Không có hợp đồng rằng phần tử có hash bằng 100 luôn nằm ở “ô 100”. Cũng không có `HashSet.get(100)` để lấy phần tử theo bucket.

### 3.2. Ví dụ với 16 bucket

Ở mô hình sử dụng các bit thấp như OpenJDK được tham chiếu, các số nguyên 1, 17 và 33 có thể cùng rơi vào bucket 1 khi bảng dài 16.

~~~text
bucket 0:  ...
bucket 1:  [key=1] -> [key=17] -> [key=33]
bucket 2:  ...
...
bucket 15: ...
~~~

Sơ đồ chỉ minh họa một bucket có nhiều mục; nó không được đọc trực tiếp từ một đối tượng `HashSet` đang chạy.

Nếu ba khóa khác nhau được lưu, size của set là 3 dù mới dùng một bucket trong ví dụ này. Một bucket không bị giới hạn chỉ chứa một thành viên.

### 3.3. Size, capacity và số bucket đang dùng là ba con số khác nhau

| Đại lượng | Ý nghĩa |
|---|---|
| `size` | Số thành viên/khóa hiện có |
| Capacity | Số bucket của bảng nền khi đã cấp |
| Số bucket không rỗng | Bao nhiêu ngăn đang có ít nhất một mục |

Va chạm làm nhiều khóa cùng bucket, nên số bucket không rỗng có thể nhỏ hơn size.

Capacity lớn hơn size không có nghĩa đã có các thành viên rỗng hoặc `null` trong set. Các bucket chưa dùng là vùng lưu trữ nội bộ, không phải phần tử của tập hợp.

## 4. Va chạm bucket khác phần tử trùng

### 4.1. Cùng bucket chưa chắc cùng hash

Với 16 bucket, hai mã băm khác nhau vẫn có thể cho cùng chỉ số sau khi thu hẹp vào khoảng 0..15.

Ví dụ hash 1 và hash 17 cùng có thể vào bucket 1. Nếu chỉ so chỉ số bucket rồi kết luận trùng, cấu trúc sẽ làm mất rất nhiều giá trị khác nhau.

Triển khai có thể kiểm tra mã băm đã lưu trước khi cần so sánh khóa. Không phải mọi khóa cùng bucket nhất thiết làm phát sinh một lần gọi `equals`; các bước lọc nội bộ có thể loại nhanh ứng viên không phù hợp.

### 4.2. Cùng hash cũng chưa chắc bằng nhau

Hai đối tượng khác nhau có thể có cùng mã băm hoàn chỉnh. Đây là một loại va chạm hash.

Một `HashSet` đúng phải vẫn giữ cả hai nếu chúng không bằng nhau theo hợp đồng của khóa. Chương trình dùng hai khóa thử nghiệm A và B đều có hash 7 để kiểm chứng việc này.

~~~text
hash(A) = 7
hash(B) = 7
A khong equals B

add(A) -> true
add(B) -> true
size = 2
~~~

Mã băm không phải mã định danh duy nhất, không phải bằng chứng hai đối tượng giống nhau và không phải giá trị nên dùng để loại trùng một mình.

### 4.3. Điều kiện một chiều của equals/hashCode

Hai đối tượng bằng nhau theo `equals` phải có cùng `hashCode`. Chiều ngược không bắt buộc.

Đây là yêu cầu trong [hợp đồng Object.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()).

~~~text
equals true -> hashCode phai bang nhau
hashCode bang nhau -> van can xet equals
~~~

Nếu một lớp ghi đè `equals` nhưng không cung cấp `hashCode` tương ứng, set băm có thể không quản lý các đối tượng theo định nghĩa trùng mà tác giả muốn. Cấu trúc không thể sửa hộ một hợp đồng khóa sai.

### 4.4. Hash ổn định theo dữ liệu khóa, không nhất thiết theo cả đời ứng dụng

Khi phần tử đang là khóa trong set băm, các thông tin dùng để so sánh và băm phải được quản lý ổn định. Nếu sửa các trường đó ngay khi phần tử vẫn nằm trong set, việc tìm/xóa có thể không còn hoạt động theo mong muốn; hợp đồng set không quy định hành vi cho thay đổi ảnh hưởng equality như vậy.

Điều này không có nghĩa mọi trường trong đối tượng đều phải bất biến trong mọi thiết kế. Điều quan trọng là những trường tham gia tiêu chí thành viên.

Nếu bảng tăng kích thước, không được coi đó là cơ chế tự sửa vấn đề một khóa đã bị đổi hash sau khi thêm.

## 5. Một số chi tiết của OpenJDK 17: trộn hash, chọn bucket và tăng bảng

Các thông tin dưới đây mô tả bản mã nguồn được tham chiếu, không phải yêu cầu bắt buộc mọi triển khai `Set` phải dùng cùng công thức.

### 5.1. Trộn bit trước khi chọn bucket

Trong [HashMap OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java), hash của khóa khác `null` được xử lý bằng cách kết hợp nó với bản dịch phải không dấu 16 bit.

Mô hình phép tính:

~~~text
raw    = key.hashCode()
spread = raw XOR (raw >>> 16)
index  = spread AND (capacity - 1)
~~~

Capacity trong cách tính này là lũy thừa của 2. Việc đưa ảnh hưởng các bit cao xuống thấp giúp tránh chỉ nhìn một nhóm bit thấp chưa có phân bố tốt.

Bước trộn không làm hai mã băm bằng nhau thành khác nhau, và không bảo đảm mọi khóa đều vào bucket riêng. Nó cũng không biến `hashCode` thông thường thành một hàm băm mật mã.

### 5.2. Bucket phụ thuộc kích thước bảng

Khi đổi từ 16 lên 32 bucket, thêm một bit được dùng trong mặt nạ. Khóa 17 đang ở bucket 1 của mô hình 16 có thể chuyển sang bucket 17 của mô hình 32.

Số 1 vẫn ở bucket 1; số 33 có thể vẫn cùng bucket với 1. Tăng bảng có thể tách một số va chạm, không có nghĩa loại bỏ mọi va chạm.

Chương trình tính hai cột bucket với capacity giả định 16 và 32. Nó không đọc capacity thật của `HashSet` và không hứa các đối tượng thử nghiệm đang dùng đúng những bảng đó ở thời điểm in.

### 5.3. Load factor diễn đạt mức tải cho việc tăng

**Hệ số tải (load factor)** là tham số giúp xác định khi nào bảng cần tăng theo số khóa đang có. Nó không phải tỷ lệ bucket không rỗng được đo trực tiếp.

Với capacity c và hệ số tải α, ngưỡng số khóa thường được tính gần c×α, có xử lý số nguyên và giới hạn trong triển khai.

Ví dụ thông thường với c = 16 và α = 0,75 cho ngưỡng 12. Ở triển khai đang xét, thêm một khóa mới làm size vượt ngưỡng này có thể kích hoạt tăng bảng. Nếu chỉ thêm lại khóa cũ, size không tăng theo cách đó.

[Tài liệu HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) giải thích quan hệ giữa capacity, load factor và việc tăng bảng.

### 5.4. Tăng bảng là công việc thật

Khi tăng, phải có bảng bucket lớn hơn và phân bố lại các mục theo vị trí mới. Mục đích là giữ quá trình tìm kiếm hiệu quả khi số phần tử tăng.

Trong OpenJDK được nêu, mã băm đã lưu trong các mục được dùng khi phân bố lại; không nên diễn đạt đơn giản rằng mọi lần resize nhất thiết gọi lại `hashCode()` của từng đối tượng.

Một lần thêm gây tăng có thể tốn nhiều công việc hơn lần thêm bình thường. Vì vậy, hiệu năng tốt trung bình/khấu hao không phải một cam kết thời gian tối đa cố định cho từng lời gọi.

### 5.5. Bucket đông có thể đổi cách tổ chức

Một bucket có thể chứa một chuỗi các mục. Khi số mục và kích thước bảng đạt điều kiện nội bộ phù hợp, OpenJDK có thể chuyển vùng đó sang cấu trúc cây; khi bảng còn nhỏ, việc tăng bảng có thể được ưu tiên.

Không nên học một câu thiếu điều kiện như “cứ có đúng N phần tử va chạm là luôn thành cây”. Cũng không suy ra rằng mọi lần truy cập sau đó được bảo đảm O(log n) trong mọi tình huống khóa và so sánh.

Cơ chế cây là một biện pháp xử lý một số tình huống va chạm nặng. Nó không thay thế việc thiết kế `hashCode` hợp lý, không làm HashSet trở thành TreeSet và không tạo thứ tự sắp xếp toàn bộ set.

## 6. Null, thứ tự duyệt và những điều cơ chế băm không bảo đảm

### 6.1. Vì sao HashSet cho một null?

Map hậu thuẫn cho phép khóa `null`. `HashSet` dùng điều đó để biểu diễn một thành viên `null`, vẫn gắn giá trị đánh dấu khác `null`.

Lần đầu `add(null)` có thể trả true; lần sau trả false. Kích thước chỉ tính một thành viên null.

Ở mô hình chọn bucket của OpenJDK đang xét, `null` có hash nội bộ 0. Bucket 0 không phải khu vực dành riêng cấm các khóa khác: một khóa khác có chỉ số bucket 0 vẫn có thể cùng được quản lý ở đó.

### 6.2. HashSet không lưu thứ tự chèn hay thứ tự tăng dần

Thứ tự duyệt chịu ảnh hưởng bảng và cách các mục được sắp bên trong; API không hứa giữ một thứ tự cụ thể. Khi bảng tăng hoặc dữ liệu thay đổi, không nên dựa vào một thứ tự từng quan sát.

Nếu cần thứ tự gặp đầu tiên, hãy chọn một cấu trúc/hợp đồng giữ thứ tự. Nếu cần sắp xếp, hãy thực hiện bước sắp xếp hoặc dùng một tập hợp có hợp đồng phù hợp.

Trong ví dụ, việc in các thành viên theo thứ tự tăng dần được làm bằng một bước riêng chỉ để kết quả dễ đối chiếu. Nó không chứng minh `HashSet` tự sắp xếp.

### 6.3. Mã băm của cả set khác mã băm từng phần tử

`set.hashCode()` là mã băm của đối tượng tập hợp theo hợp đồng `Set`, được xây từ các mã băm thành viên. Nó không trả bucket của một phần tử, capacity hay size.

[Set.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()) định nghĩa mã băm set bằng tổng các mã băm thành viên, với null đóng góp 0. Quy tắc này giúp các set bằng nhau có mã băm bằng nhau mà không phụ thuộc thứ tự duyệt.

Cần phân biệt:

| Khái niệm | Dùng để hiểu điều gì? |
|---|---|
| `element.hashCode()` | Mã băm của khóa/phần tử |
| Hash đã trộn nội bộ | Hỗ trợ tính vị trí trong bảng cụ thể |
| Chỉ số bucket | Vùng ứng viên của một bảng có capacity cụ thể |
| `set.hashCode()` | Mã băm của cả tập hợp theo hợp đồng equality của set |
| `set.size()` | Số thành viên |

## 7. Chương trình hoàn chỉnh: đối chiếu HashSet với mô hình map

Ví dụ dưới đây không tự triển khai một bảng băm hoàn chỉnh. Nó dùng `HashMap` công khai để mô hình hóa cách ghi nhận thành viên, rồi so kết quả với một `HashSet` thật.

Phần bucket là một phép tính giải thích của OpenJDK 17 với capacity cho trước, không phải kiểm tra các trường riêng của `HashSet`.

### 7.1. Mã nguồn

Lưu thành `HashSetTableDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class HashSetTableDemo {
    // Khoa thi nghiem: co tinh cho moi id cung hash de tao va cham.
    record SameHashKey(String id) {
        SameHashKey {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    // Mo hinh vi tri bucket cua OpenJDK 17, khong doc bang noi bo.
    static int modeledBucket(Object key, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0) {
            throw new IllegalArgumentException("capacity must be a positive power of two");
        }
        int raw = key == null ? 0 : key.hashCode();
        int spread = raw ^ (raw >>> 16);
        return spread & (capacity - 1);
    }

    static List<String> sortedMembers(Set<String> values) {
        Set<String> ordered = new TreeSet<>(
                Comparator.nullsFirst(Comparator.naturalOrder()));
        ordered.addAll(values);
        return new java.util.ArrayList<>(ordered);
    }

    public static void main(String[] args) {
        Set<String> actual = new HashSet<>();
        Map<String, Boolean> membershipModel = new HashMap<>();
        for (String key : Arrays.asList("java", "spring", "java", null, null)) {
            boolean setAdded = actual.add(key);
            boolean modelAdded = membershipModel.put(key, Boolean.TRUE) == null;
            System.out.printf("add(%s): set=%s, model=%s, sameKeys=%s, size=%d%n",
                    key, setAdded, modelAdded,
                    actual.equals(membershipModel.keySet()), actual.size());
        }
        System.out.println("members sorted for display: " + sortedMembers(actual));
        System.out.printf("contains java: set=%s, model=%s%n",
                actual.contains("java"), membershipModel.containsKey("java"));
        boolean setRemoved = actual.remove("java");
        boolean modelRemoved = membershipModel.remove("java") != null;
        System.out.printf("remove java: set=%s, model=%s, sameKeys=%s%n",
                setRemoved, modelRemoved, actual.equals(membershipModel.keySet()));

        System.out.println("modeled buckets: key, capacity16, capacity32");
        for (Integer key : Arrays.asList(1, 17, 33, null)) {
            System.out.printf("%s, %d, %d%n", key,
                    modeledBucket(key, 16), modeledBucket(key, 32));
        }

        Set<SameHashKey> collisions = new HashSet<>();
        System.out.println("same-hash A: " + collisions.add(new SameHashKey("A")));
        System.out.println("same-hash B: " + collisions.add(new SameHashKey("B")));
        System.out.println("same-hash A again: " + collisions.add(new SameHashKey("A")));
        System.out.println("same-hash size: " + collisions.size());
        System.out.println("same-hash ids sorted: "
                + collisions.stream().map(SameHashKey::id).sorted().toList());

        Map<String, Boolean> unsafeNullValueModel = new HashMap<>();
        unsafeNullValueModel.put("present", null);
        boolean alreadyPresent = unsafeNullValueModel.containsKey("present");
        Boolean previous = unsafeNullValueModel.put("present", Boolean.TRUE);
        System.out.printf("general map: alreadyPresent=%s, previousIsNull=%s%n",
                alreadyPresent, previous == null);

        Set<Integer> resizedByImplementation = new HashSet<>();
        for (int value = 0; value < 100; value++) {
            resizedByImplementation.add(value);
        }
        boolean allFound = true;
        for (int value = 0; value < 100; value++) {
            allFound &= resizedByImplementation.contains(value);
        }
        System.out.printf("after 100 distinct adds: size=%d, allFound=%s%n",
                resizedByImplementation.size(), allFound);

        Set<String> differentSize = new HashSet<>(List.of("java", "spring"));
        System.out.println("set hashCode is not size: "
                + (differentSize.hashCode() != differentSize.size()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 HashSetTableDemo.java
java HashSetTableDemo
~~~

### 7.2. Kết quả stdout

~~~text
add(java): set=true, model=true, sameKeys=true, size=1
add(spring): set=true, model=true, sameKeys=true, size=2
add(java): set=false, model=false, sameKeys=true, size=2
add(null): set=true, model=true, sameKeys=true, size=3
add(null): set=false, model=false, sameKeys=true, size=3
members sorted for display: [null, java, spring]
contains java: set=true, model=true
remove java: set=true, model=true, sameKeys=true
modeled buckets: key, capacity16, capacity32
1, 1, 1
17, 1, 17
33, 1, 1
null, 0, 0
same-hash A: true
same-hash B: true
same-hash A again: false
same-hash size: 2
same-hash ids sorted: [A, B]
general map: alreadyPresent=true, previousIsNull=true
after 100 distinct adds: size=100, allFound=true
set hashCode is not size: true
~~~

### 7.3. Đọc kết quả theo từng cơ chế

Mỗi lần thêm vào `HashSet` được đối chiếu với việc đặt cùng khóa vào map mô hình. `sameKeys=true` cho biết các tập khóa bằng nhau; đây là so sánh thành viên, không phải so sánh thứ tự.

Hai lần thêm java cho true rồi false; hai lần thêm null cũng vậy. Điều này xuất phát từ tính duy nhất của khóa trong map, không từ việc các value đánh dấu có khác nhau hay không.

`members sorted for display` dùng một `TreeSet` với comparator chấp nhận null để in ổn định. HashSet gốc vẫn không có bảo đảm thứ tự.

Cột modeled buckets cho thấy 1, 17, 33 cùng bucket ở capacity 16, nhưng 17 tách sang bucket 17 khi dùng capacity 32. Cả hai bảng chỉ là giả định đầu vào cho hàm `modeledBucket`.

`SameHashKey` là record có equality theo id và một `hashCode` cố ý luôn trả 7. Cách băm này đúng điều kiện “bằng nhau thì cùng hash” nhưng có phân bố rất kém; chỉ dùng để tạo va chạm trong bài học, không phải mẫu thiết kế băm nên dùng trong ứng dụng.

A và B cùng hash vẫn được giữ thành hai thành viên. Thêm một A khác lại trả false vì equality theo id nhận diện A đã có.

Map tổng quát ở cuối có khóa present đang gắn value null. `containsKey` báo đã có khóa trong khi giá trị cũ của put vẫn là null. Đây là lý do mô hình set cần quản lý một giá trị đánh dấu không null.

Sau 100 lần thêm số nguyên khác nhau, size là 100 và mọi giá trị đều tìm thấy. Chương trình chỉ kiểm tra nội dung qua API; nó không đọc được số lần resize hay capacity thật.

Dòng cuối dùng một ví dụ có mã băm set khác size để nhắc rằng hai phương thức có hai hợp đồng. Nó không khẳng định chúng không bao giờ tình cờ cho cùng một số.

## 8. Mô hình hiệu năng phải có điều kiện

### 8.1. Khi nào nói các thao tác cơ bản gần O(1)?

Với hàm băm có phân bố tốt, số ứng viên trong bucket được giữ hợp lý và chi phí `hashCode/equals` không quá lớn, các thao tác tìm, thêm, xóa có hiệu năng kỳ vọng tốt.

Đối với thêm nhiều phần tử, còn cần phân bổ chi phí những lần tăng bảng trên cả chuỗi thao tác. Không được biến kết luận kỳ vọng/khấu hao thành lời hứa trường hợp xấu nhất hằng số cho mọi đầu vào.

Một cách tách chi phí là:

~~~text
tinh hash cua khoa
+ chon bucket
+ kiem tra cac ung vien can thiet
+ cap/cap nhat muc
+ cong viec tang bang neu lan nay can
~~~

Nếu `hashCode` quét một chuỗi rất dài hoặc `equals` làm công việc nặng, thời gian đó vẫn phải được tính. Hằng số theo số thành viên không đồng nghĩa hằng số theo mọi kích thước dữ liệu.

### 8.2. Vì sao capacity ảnh hưởng cả bộ nhớ và duyệt?

Tài liệu HashSet mô tả chi phí duyệt tỷ lệ với số thành viên cộng capacity của map hậu thuẫn. Một bảng rất rộng nhưng ít phần tử có thể lãng phí bộ nhớ và khiến việc đi qua bảng kém phù hợp hơn.

Đặt capacity quá thấp có thể tăng số lần cấp/tăng bảng; đặt quá cao có thể giữ nhiều bucket chưa dùng. Load factor là một đánh đổi liên quan, không phải tham số cứ càng thấp càng tốt.

Vì thế, không nên cấp trước một số cực lớn chỉ để khẳng định “không bao giờ resize”. Cần dựa vào số lượng thành viên dự kiến và kiểu thao tác thực tế.

### 8.3. Constructor capacity không phải số thành viên được điền

`new HashSet<>(16)` tạo một set rỗng, không tạo 16 phần tử và không bảo đảm rằng phải thêm đủ 16 khóa mới rồi mới xét tăng bảng.

Với hệ số tải mặc định 0,75, cần phân biệt số bucket dự kiến với ngưỡng số khóa. Trong bản OpenJDK được nêu, việc cấp mảng bucket còn được trì hoãn đến lúc cần; constructor rỗng không đồng nghĩa ngay lập tức đã tạo một mảng chứa đủ các mục dữ liệu.

Không có getter công khai của `HashSet` để lấy capacity thật. Ví dụ học tập dùng capacity cố định phải nói rõ đó là mô hình, như chương trình ở bài này.

### 8.4. Chọn cấu trúc theo câu hỏi dữ liệu

HashSet phù hợp khi cần quản lý thành viên duy nhất và kiểm tra có/không theo equality. Nếu cần lưu giá trị ứng với khóa, dùng một `Map` có thể biểu diễn mục tiêu trực tiếp hơn.

Nếu cần giữ số lần xuất hiện, set một mình không giữ thông tin đó. Nếu cần thứ tự, set băm thông thường cũng chưa đáp ứng hợp đồng trình bày.

Không dùng khả năng tìm kiếm nhanh để bỏ qua việc xác định đúng mô hình dữ liệu.

## 9. Các điều kiện sử dụng cần giữ

### 9.1. Khóa có hợp đồng đúng và ổn định

Định nghĩa `equals/hashCode` theo cùng tiêu chí thành viên. Khi có thể, dùng khóa có các thành phần ổn định như record chứa chuỗi bất biến hoặc các kiểu giá trị phù hợp.

Nếu phần tử có các trường có thể thay đổi, hãy biết trường nào tham gia equality/hash. Không sửa chúng ngay trong thời gian cấu trúc đang dùng phần tử làm khóa.

### 9.2. HashSet không tự đồng bộ

Sử dụng map hậu thuẫn không làm các thao tác trên `HashSet` tự an toàn cho nhiều luồng cùng sửa. Cũng không thể dựa vào fail-fast để bảo vệ một quy trình đồng thời.

Nếu cần chia sẻ để ghi, phải có cách phối hợp hoặc cấu trúc đáp ứng yêu cầu. Ví dụ trong bài dùng một luồng và không chứng minh hành vi đồng thời.

### 9.3. Đọc mã nguồn để hiểu, không ràng buộc nghiệp vụ vào chi tiết riêng

Các công thức trộn hash, hình thức bucket và điều kiện chuyển cây có thể khác giữa các triển khai/phiên bản. Mã ứng dụng nên dựa vào hợp đồng set và những bảo đảm hiệu năng được tài liệu hóa phù hợp.

Những điều cần giữ bền vững hơn các con số nội bộ là: phần tử là khóa, equality/hash phải đúng, va chạm không đồng nghĩa trùng, và thứ tự không được suy đoán từ bảng băm.

## 10. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| HashSet kế thừa HashMap | Nó dùng map như một thành phần bên trong |
| Phần tử set là value của map | Phần tử được dùng làm key; value chỉ là dấu hiện diện |
| Mỗi phần tử cần một giá trị đánh dấu riêng | Dấu có thể dùng chung; tính duy nhất nằm ở key |
| Put trả null luôn nghĩa là key mới | Chỉ suy ra được khi biết map không lưu value null cho key đã có |
| Hash bằng nhau thì phải là cùng phần tử | Vẫn phải xét equality |
| Cùng bucket thì hash chắc chắn bằng nhau | Chỉ số bucket là kết quả thu hẹp, nhiều hash khác nhau có thể trùng bucket |
| Một bucket chỉ được một phần tử | Có cơ chế quản lý nhiều mục trong cùng bucket |
| Capacity bằng size | Capacity là số bucket, size là số khóa |
| Null chiếm một bucket riêng cấm khóa khác | Nó là một khóa được xử lý đặc biệt; bucket vẫn có thể có khóa khác |
| Resize sửa được mọi khóa đã đổi hash | Không được dựa vào resize để sửa hợp đồng khóa bị vi phạm |
| Bucket thành cây thì cả set có thứ tự | Tổ chức cục bộ của bucket không tạo hợp đồng sắp xếp toàn set |
| Tìm kiếm O(1) nghĩa là mọi lần đều cùng độ trễ | Cần xét băm, so sánh, va chạm, cấp phát và tăng bảng |
| set.hashCode là vị trí bucket hoặc số phần tử | Đó là mã băm của cả set theo hợp đồng Set |
| new HashSet(16) chứa sẵn 16 phần tử | Nó vẫn rỗng; tham số liên quan dung lượng bảng |

## 11. Bài tập tự kiểm tra

### Bài 1: quan hệ key/value

Set chứa ba thành viên A, B, C. Trong mô hình map hậu thuẫn, có bao nhiêu key và cần bao nhiêu loại value nghiệp vụ?

**Giải thích:** Có ba key; không cần value nghiệp vụ riêng cho từng key. Các key có thể cùng gắn một đối tượng đánh dấu hiện diện.

### Bài 2: trùng hash

Hai khóa có hash 7 nhưng equals false. HashSet có buộc chỉ giữ một khóa không?

**Giải thích:** Không. Bảng phải xử lý va chạm và giữ cả hai thành viên khác nhau khi dữ liệu hợp lệ.

### Bài 3: cùng bucket

Vì sao hash 1 và 17 có thể cùng vào bucket 1 khi có 16 bucket nhưng không cùng bucket khi có 32 trong mô hình của bài?

**Giải thích:** Với lũy thừa 2, mặt nạ dùng các bit thấp theo capacity. Tăng từ 16 lên 32 dùng thêm một bit; hash 17 có thể được tách sang chỉ số 17. Đây là vị trí của bảng cụ thể, không phải danh tính khóa.

### Bài 4: map có value null

Map đã có `K -> null`. Put K với một dấu khác null trả null. Có thể kết luận K trước đó chưa có không?

**Giải thích:** Không. Giá trị trả về cũ có thể null vì key đã ánh xạ tới null. Mô hình set tránh nhập nhằng bằng cách không dùng null làm value đánh dấu cho thành viên hiện có.

### Bài 5: size và bucket

Có 20 thành viên nhưng chỉ 7 bucket không rỗng do va chạm. Size của set là 7 hay 20?

**Giải thích:** 20. Số bucket được dùng không phải số thành viên.

### Bài 6: đầu vào thay đổi

Một đối tượng đã được thêm rồi bị đổi trường dùng tính hash. Có nên đợi lần tăng bảng để “tính lại và sửa vị trí” không?

**Giải thích:** Không. Hãy bảo toàn hợp đồng khóa trong suốt thời gian nó được giữ. Resize không phải cơ chế sửa một thay đổi dữ liệu làm vi phạm các giả định của set.

### Bài 7: thứ tự

Một HashSet các số nguyên tình cờ in theo thứ tự tăng dần. Có thể coi đó là một sorted set không?

**Giải thích:** Không. Cần một hợp đồng sắp xếp hoặc bước sắp xếp rõ ràng. Thứ tự quan sát được không trở thành bảo đảm của HashSet.

Nhìn `HashSet` như một tập các khóa của bảng băm giúp nối hợp đồng “thành viên duy nhất” với cơ chế lưu trữ cụ thể. Khả năng tìm nhanh đến từ việc chọn vùng ứng viên bằng hash; tính đúng vẫn dựa vào equality, quản lý va chạm và các điều kiện của khóa.
