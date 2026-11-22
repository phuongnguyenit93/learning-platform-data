# Phân biệt hợp đồng API với cách tổ chức nội bộ của bảng băm trong Java

## 1. Hai tầng cần phân biệt

Khi làm việc với `HashMap`, `HashSet` và các cấu trúc băm trong Java, có hai câu hỏi khác nhau:

- **Hợp đồng API (contract):** Người sử dụng có thể tin vào hành vi nào khi gọi `put`, `get`, `containsKey`, `add`, `contains`, `equals` hoặc `hashCode`? Phần nào được tài liệu của kiểu Java cam kết?
- **Cách tổ chức nội bộ (implementation):** Thư viện tổ chức các phần tử thành bucket như thế nào, chọn chỉ số bucket bằng cách nào, xử lý va chạm, mở rộng bảng và tối ưu tìm kiếm ra sao?

**Lớp bên ngoài là cam kết; lớp bên trong là cơ chế để thực hiện cam kết.** Mã ứng dụng đúng nên dựa vào những hành vi đã được quy định trong hợp đồng của kiểu mà nó sử dụng. Những chi tiết cụ thể của một bản triển khai có thể thay đổi theo phiên bản JDK, hoặc giữa các thư viện, dù hành vi công khai vẫn giữ nguyên.

Phân biệt thêm **ba cấp hợp đồng** thường xuyên xuất hiện cùng nhau:

1. `Object.equals(Object)` và `Object.hashCode()` định nghĩa cách các đối tượng thể hiện quan hệ bằng nhau và mã băm. Đây là trách nhiệm của *kiểu khóa/phần tử*.
2. `Map<K,V>` và `Set<E>` quy định ngữ nghĩa collection, ví dụ khóa duy nhất theo quan hệ bằng nhau và phần tử của tập hợp không lặp.
3. `HashMap`, `HashSet` là các lớp triển khai cụ thể, với một số hành vi công khai bổ sung (như chấp nhận `null` của `HashMap`) và nhiều chi tiết cài đặt không nên bị mã ứng dụng phụ thuộc.

Một đặc tính không được `Map` nói chung bảo đảm vẫn có thể được một lớp triển khai cụ thể **cam kết trong API của lớp đó**. Ngược lại, quan sát tình cờ trên một JVM không tự biến hành vi ấy thành hợp đồng.

## 2. Những hành vi phải tin cậy theo hợp đồng

### 2.1. Bình đẳng khóa và mã băm

Với khóa khác `null`, quy tắc nền tảng là:

- Nếu `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`.
- Nếu `a.equals(b)` là `false`, mã băm **có thể bằng hoặc khác nhau**; việc hai đối tượng khác nhau có cùng mã băm (*collision*) là hợp lệ.
- Trong một lần chạy, nếu thông tin được dùng trong phép so sánh `equals` không thay đổi, các lần gọi `hashCode()` trên một đối tượng phải nhất quán.
- `equals` còn phải tuân thủ các điều khoản phản xạ, đối xứng, bắc cầu, nhất quán và không bằng `null`.

Không có điều khoản nào yêu cầu **mã băm duy nhất cho mỗi khóa** hoặc bắt buộc mã băm có giá trị dương. Mã băm chỉ là một gợi ý để tổ chức việc tìm kiếm; bình đẳng logic mới quyết định liệu hai khóa có đại diện cho cùng một entry hay không.

### 2.2. Ngữ nghĩa của `Map` và `HashMap`

Một `Map` biểu diễn ánh xạ từ **mỗi khóa tới tối đa một giá trị**. Với một `HashMap` được cài đặt đúng và các khóa tuân thủ hợp đồng:

- `put(k, v)` gắn giá trị `v` cho khóa logic `k`. Nếu đã có khóa tương đương, ánh xạ cũ được thay thế; hai khóa bằng nhau không tạo hai entry độc lập. `HashMap.put` trả về giá trị gắn trước đó, hoặc `null` nếu trước đó không có ánh xạ hoặc đã ánh xạ tới `null`.
- `get(k)` trả về giá trị gắn với khóa tương đương, hoặc `null` khi không có ánh xạ. Với `HashMap`, `null` cũng có thể là **giá trị được lưu**, nên dùng `containsKey(k)` để phân biệt hai trường hợp.
- `size()` trả số ánh xạ đang có; `remove(k)` loại bỏ ánh xạ cho khóa tương đương.
- `HashMap` chấp nhận **một khóa `null`** và nhiều giá trị `null`. Đây là đặc tính được tài liệu `HashMap` công bố; không được suy rộng sang mọi `Map`. Ví dụ `ConcurrentHashMap` và `Map.of(...)` không chấp nhận khóa hoặc giá trị `null`.

Một số thao tác sửa đổi là *optional operations* ở cấp giao diện `Map`: không phải bất kỳ `Map` nào cũng cho phép `put` hay `remove`. `HashMap` là lớp có hỗ trợ các thao tác sửa đổi ấy.

### 2.3. Ngữ nghĩa của `Set` và `HashSet`

Một `Set` không chứa hai phần tử bằng nhau. Với `HashSet`:

- `add(e)` trả `true` nếu phần tử mới được thêm, và trả `false` nếu đã có phần tử tương đương.
- `contains(e)` kiểm tra có phần tử tương đương hay không, không phụ thuộc vào việc phần tử ấy có **cùng địa chỉ/tham chiếu** với `e`.
- Các phần tử có cùng mã băm nhưng `equals` trả `false` **vẫn có thể cùng tồn tại trong tập hợp**.
- `HashSet` cho phép một phần tử `null`; một số triển khai `Set` khác có thể áp đặt quy tắc riêng.

Đây là những điều cần kiểm tra thông qua API, không cần biết tập hợp dùng một mảng bucket, danh sách, cây hay một tổ chức khác.

## 3. Bucket, collision và resize thuộc tầng triển khai

Có thể hình dung hoạt động điển hình của một bảng băm như sau:

```text
put(key, value)
    |
    v
lấy hashCode của key
    |
    v
trộn/chuyển đổi bit (nếu triển khai cần)
    |
    v
xác định vùng chứa/bucket từ dung lượng hiện tại
    |
    v
xử lý các khóa cùng vùng bằng so sánh bình đẳng
    |
    v
thêm entry mới hoặc cập nhật entry tương đương
```

Đây là **sơ đồ khái niệm**, không phải lời hứa về thứ tự gọi phương thức, công thức chỉ số, cấu trúc nút hay số bước của một phiên bản `HashMap` cụ thể.

Các thuật ngữ thường gặp:

- **Bucket:** một vị trí hoặc nhóm chứa các entry được phân bố bởi hàm băm. Số bucket và cách ánh xạ mã băm tới bucket là chi tiết cài đặt.
- **Collision:** hai khóa có thể được xét trong cùng một bucket, hoặc có cùng mã băm, tùy cách diễn đạt. Việc trùng `hashCode` là điều tự nhiên; các khóa khác nhau vẫn phải được phân biệt khi so sánh bằng nhau.
- **Capacity:** kích thước/khả năng chứa nội bộ của bảng trong một cấu trúc cụ thể.
- **Load factor:** tham số liên quan đến mức độ đầy của bảng và chính sách mở rộng trong các triển khai như `HashMap`.
- **Resize/rehash:** quá trình nội bộ điều chỉnh cấu trúc và phân bố lại entry khi bảng cần thêm không gian.

`HashMap` có các constructor công khai cho phép người dùng cung cấp **initial capacity** và **load factor**, nên *khái niệm* và các tham số này là một phần của API lớp. Tuy nhiên, chi tiết như số bucket thực tế sau khi làm tròn, ngưỡng phân bổ node, cách trộn bit hoặc thời điểm chính xác cây hóa bucket không phải là quy tắc ngữ nghĩa của `Map` mà ứng dụng có thể dựa vào.

Trong một số bản OpenJDK, bucket có thể dùng node dạng danh sách và đôi khi chuyển sang cấu trúc cây để xử lý trường hợp collision cao. Điều đó hữu ích khi đọc mã nguồn JDK hoặc chẩn đoán hiệu năng, nhưng **không phải điều kiện cần** để hiểu và sử dụng đúng `put/get/equals/hashCode`; đừng viết logic nghiệp vụ đòi hỏi đúng một số node, ngưỡng treeification hay thứ tự duyệt của nội bộ OpenJDK.

## 4. Ví dụ Java 17: cùng hợp đồng, cấu hình bảng khác nhau

Một lỗi dễ mắc khi đọc mã nguồn JDK là lấy dung lượng bảng hoặc cách tổ chức bucket để dự đoán kết quả nghiệp vụ. Thử nghiệm sau tạo hai `HashMap` với dung lượng ban đầu khác nhau, đưa vào cùng các khóa **cố ý va chạm**, rồi chỉ kiểm tra các giá trị mà API cam kết.

Lưu vào `HashApiContractDemo.java`:

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class HashApiContractDemo {
    record Key(String id) {
        @Override
        public int hashCode() {
            return 1; // Cố ý gây va chạm, vẫn tương thích với equals của record.
        }
    }

    private static String observe(Map<Key, String> map) {
        map.put(new Key("A"), "a1");
        map.put(new Key("B"), "b1");
        String old = map.put(new Key("A"), "a2");
        return "size=" + map.size()
                + ", old=" + old
                + ", A=" + map.get(new Key("A"))
                + ", B=" + map.get(new Key("B"));
    }

    public static void main(String[] args) {
        System.out.println("small: " + observe(new HashMap<>(2)));
        System.out.println("large: " + observe(new HashMap<>(128)));

        Map<String, Integer> ordered = new LinkedHashMap<>();
        ordered.put("B", 2);
        ordered.put("A", 1);
        ordered.put("B", 20);
        System.out.println("linked keys: "
                + String.join(" -> ", ordered.keySet()));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 HashApiContractDemo.java
java HashApiContractDemo
~~~

Đầu ra:

~~~text
small: size=2, old=a1, A=a2, B=b1
large: size=2, old=a1, A=a2, B=b1
linked keys: B -> A
~~~

Hai `HashMap` có tham số dung lượng ban đầu khác nhau nhưng cùng cho kết quả qua `put`, `get` và `size`: khóa A mới tạo vẫn bằng khóa A đã lưu, khóa B khác A dù có chung mã băm, và lần cập nhật A trả về giá trị cũ. Đó là **hợp đồng quan sát được**. Bài không đọc hoặc khẳng định số bucket thực sự đã được cấp phát, ngưỡng cây hóa hay trình tự gọi `equals()`; các yếu tố ấy tùy thuộc triển khai.

`LinkedHashMap` được đưa vào để đối chiếu một cam kết khác: thứ tự chèn của nó được công bố. Thay giá trị B không chuyển B tới cuối trong chế độ mặc định, nên có thể kiểm tra dãy `B -> A`. Không kiểm tra thứ tự lặp của hai `HashMap`, vì chúng không hứa thứ tự chèn.

Ví dụ dùng hàm băm cố định chỉ để cô lập hợp đồng equality. Hàm băm phân bố kém có thể làm giảm hiệu năng với dữ liệu lớn; sự đúng đắn của các thao tác vẫn phụ thuộc vào `equals`/`hashCode` tương thích và khóa ổn định.

## 5. Bảng so sánh: cam kết công khai và chi tiết bên trong

| Chủ đề | Hợp đồng có thể dựa vào | Chi tiết không nên coi là cam kết |
| --- | --- | --- |
| Khóa bằng nhau | `HashMap` không giữ hai ánh xạ riêng cho hai khóa tương đương | Có bao nhiêu node cùng bucket, so sánh node theo đúng thứ tự nào |
| Mã băm | `equals == true` ⇒ cùng `hashCode`; collision được phép | Hàm trộn bit, phép lấy index từ hash, số bucket |
| `put/get` | Kết quả phù hợp với ánh xạ của khóa, nếu khóa tuân thủ hợp đồng | Chính xác bao nhiêu phép so sánh hoặc lần truy cập bộ nhớ |
| `null` | `HashMap` hỗ trợ khóa và giá trị `null`; `HashSet` hỗ trợ phần tử `null` | `null` được đánh dấu hoặc cất giữ nội bộ bằng kỹ thuật nào |
| Thứ tự | `LinkedHashMap` mặc định bảo toàn thứ tự chèn; `HashMap` không bảo đảm thứ tự | Thứ tự duyệt tình cờ xuất hiện ở một dung lượng/phiên bản JVM |
| Collision | Các khóa khác nhau cùng hash vẫn có thể tồn tại | Bucket là danh sách, cây, hay tối ưu hóa nào khác |
| Mở rộng | Sau khi mở rộng, ngữ nghĩa ánh xạ không thay đổi vì riêng thao tác mở rộng | Thời điểm, ngưỡng, công thức resize và cách phân phối lại bucket |
| Hiệu năng | `HashMap` có hiệu năng trung bình tốt cho các thao tác cơ bản khi hash phân bố thích hợp | Cam kết rằng mọi `get/put` luôn mất chính xác O(1), bất kể dữ liệu |
| Đồng thời | `HashMap` không phải collection tự đồng bộ cho chỉnh sửa đồng thời | Việc đọc/ghi không đồng bộ “tình cờ chạy được” trên máy hiện tại |

Dòng “hiệu năng” cần hiểu đúng: tài liệu `HashMap` nói về **hiệu năng kỳ vọng** cho `get` và `put` với giả định giá trị băm phân bố hợp lý. Đó không phải bảo đảm chặt chẽ rằng mọi thao tác đều có cùng thời gian bất kể collision, resize, kích thước hay các tác động JVM. Nếu tối ưu hiệu năng, hãy đo workload thật thay vì suy luận về một bucket giả định.

## 6. Hợp đồng thứ tự: chọn đúng collection

Một lỗi quen thuộc là chạy đoạn mã sau nhiều lần, thấy cùng một thứ tự rồi cho rằng `HashMap` luôn trả theo thứ tự đó. `HashMap` **không bảo đảm thứ tự duyệt**, và thứ tự cũng không được cam kết là cố định theo thời gian. Các thay đổi kích thước bảng, phân bố hash, lịch sử thêm/xóa hoặc thay phiên bản JDK có thể làm quan sát khác đi.

Nếu ứng dụng **thực sự cần thứ tự**, chọn loại có hợp đồng tương ứng:

- **`LinkedHashMap`:** mặc định duy trì thứ tự chèn; có cấu hình thứ tự truy cập cho các bài toán đặc thù. Khi dùng chế độ mặc định, cập nhật giá trị của khóa đã có không làm thay đổi thứ tự chèn.
- **`TreeMap`:** thứ tự khóa dựa trên thứ tự tự nhiên hoặc một `Comparator` được cung cấp. Với sorted map, tiêu chí so sánh của comparator quyết định tính tương đương khóa theo map; nếu muốn tuân thủ đầy đủ hợp đồng `Map` theo `equals`, thứ tự đó nên nhất quán với `equals`.
- **`HashMap`:** chọn khi cần ánh xạ với hiệu năng băm điển hình và **không cần** bảo đảm thứ tự.

Đừng dựa vào việc `HashMap` hôm nay có thể in các khóa số nguyên theo thứ tự tăng: với khóa/dung lượng cụ thể đó, thứ tự tăng chỉ là một hiện tượng cài đặt.

## 7. Hợp đồng khi khóa mutable: lỗi không nằm ở bucket

Có thể viết một lớp có `equals()` và `hashCode()` đều dựa trên trường `id` có thể sửa. Tại thời điểm chưa sửa, hai phương thức vẫn có thể đáp ứng hợp đồng. Nhưng nếu đối tượng ấy đã là khóa trong `HashMap`, sau đó sửa `id` thì map **không có nghĩa vụ tự tái cấu trúc** entry theo giá trị mã băm mới.

Ví dụ sau là **đoạn mã minh họa**, giả định `key` là một đối tượng có setter sửa trường `id` tham gia `equals/hashCode`:

```java
map.put(key, "saved");
key.setId("another-id"); // Tránh sửa thuộc tính danh tính của khóa đang lưu.
String value = map.get(key); // Có thể không tìm thấy entry đã lưu.
```

Cách xử lý: dùng **khóa bất biến** (ví dụ ID `String`, số, record gồm các thành phần bất biến) hoặc xóa khóa cũ *trước khi* sửa và chèn một khóa mới với giá trị mới. Sửa trực tiếp một object đang lưu rồi hy vọng `get` vẫn chạy được là dựa vào may rủi cài đặt.

Một record Java 17 như:

```java
record CustomerKey(String tenantId, long customerId) {}
```

có `equals/hashCode` tự sinh theo các component. Nó là ví dụ thích hợp khi mọi component đều ổn định, như `String` và `long`. **Record không tự bảo đảm bất biến sâu** nếu có component là mảng hoặc đối tượng mutable.

Hãy phân biệt lỗi do **khóa tự phá hợp đồng bình đẳng/mã băm** và vấn đề do **thuật toán bucket**. Nhiều triệu chứng lookup không nhất quán bắt nguồn từ cài đặt `equals/hashCode` sai hoặc sửa khóa, không phải từ chi tiết cấu trúc bảng băm.

## 8. Đọc source JDK thế nào mà không biến nó thành API?

Đọc source của `java.util.HashMap` trong một JDK cụ thể là rất hữu ích để hiểu:

- Cách triển khai xử lý giá trị hash và ánh xạ vào bảng hiện tại.
- Tình huống phân bổ entry mới, cập nhật entry, xử lý collision và resize.
- Cách phiên bản đó tối ưu các bucket đông phần tử hoặc hỗ trợ iterator.
- Vì sao một loại dữ liệu hoặc tải công việc tạo ra áp lực CPU/bộ nhớ.

Nhưng một **quan sát source** nên được ghi rõ phạm vi, ví dụ “trong bản OpenJDK này ...”; không suy rộng nó thành quy định bắt buộc với mọi Java. Việc Java có nhiều JDK/phiên bản khiến sự phân biệt này rất thiết thực.

Để biết có thể **phụ thuộc vào** hành vi nào, tra tài liệu Javadoc của đúng kiểu và phiên bản API đang dùng (`Map`, `Set`, `HashMap`, `HashSet`, `LinkedHashMap`, `Object`). Để biết **vì sao** triển khai hiện tại nhanh/chậm ở một tình huống, mới đọc source, benchmark và công cụ profiler.

Các khái niệm “capacity” và “load factor” vẫn quan trọng khi tối ưu cấu hình `HashMap`: chúng được mô tả trong Javadoc và một số constructor công khai. Tuy vậy, chi tiết chính xác về số bucket, cách phân phối hay ngưỡng cây hóa không được nâng thành hợp đồng chỉ vì source hiện tại dùng chúng.

## 9. Thứ tự gọi phương thức, iterator và đồng thời

### Không giả định số lần `equals()` được gọi

Mã ứng dụng không nên đếm số lần `equals` được gọi trong một lần `get`, `containsKey` hay `put` rồi dùng nó làm hành vi nghiệp vụ. Triển khai có thể tra cứu theo identity, hash, so sánh các candidate hoặc dùng tối ưu nội bộ. Vì vậy `equals` nên là phép so sánh **không gây side effect** và không phụ thuộc số lần gọi hay thời gian thực.

### Không dựa vào fail-fast như cơ chế đồng bộ

Tài liệu `HashMap` mô tả iterator có cơ chế **fail-fast** đối với một số thay đổi cấu trúc không hợp lệ khi đang duyệt, thường ném `ConcurrentModificationException`. Tuy nhiên, hành vi phát hiện là **best effort**, không phải cơ chế chắc chắn để phát hiện mọi cuộc đua dữ liệu và cũng không làm `HashMap` trở nên an toàn đa luồng.

Nếu có nhiều thread sửa đồng thời và không có đồng bộ ngoài, cần thiết kế phù hợp, chẳng hạn dùng `ConcurrentHashMap` khi đáp ứng yêu cầu. Lưu ý `ConcurrentHashMap` có **hợp đồng riêng** (ví dụ không cho phép `null`), vì thế không thể xem nó là cùng một triển khai nội bộ có thể hoán đổi mà không xét API.

### Phân biệt giao diện và lớp triển khai

Nếu khai báo `Map<String, Integer> m = new HashMap<>();`, biến `m` có kiểu `Map`, nhưng đối tượng lúc chạy là `HashMap`. Hành vi của lời gọi cần tuân thủ hợp đồng `Map`, cộng với các đặc điểm được lớp `HashMap` công bố. Nếu về sau đổi sang `Map.of(...)` hoặc `TreeMap`, hãy kiểm tra lại những đặc tính khác biệt (khả năng sửa, chấp nhận `null`, thứ tự) thay vì mặc định mọi `Map` tương đương nhau.

## 10. Tình huống thực tế để tự kiểm tra

**Tình huống A — hai khóa khác nhau cùng hash.** `k1.hashCode() == k2.hashCode()` nhưng `k1.equals(k2) == false`. `HashSet` được phép chứa cả hai, và `HashMap` phải lưu được hai ánh xạ nếu các thao tác hợp lệ. Đừng báo lỗi chỉ vì collision.

**Tình huống B — hai khóa bằng nhau.** `k1.equals(k2) == true` và `hashCode` cùng giá trị. `HashMap.put(k2, newValue)` phải cập nhật ánh xạ tương đương đã được thêm bởi `k1`. Không cần biết hai khóa đang nằm trong bucket nào.

**Tình huống C — thứ tự in có vẻ luôn giống nhau.** Nếu đang duyệt `HashMap`, không thể biến quan sát thành hợp đồng; nếu cần thứ tự chèn, dùng `LinkedHashMap`, nếu cần thứ tự sắp xếp theo khóa, xem `TreeMap`.

**Tình huống D — giá trị đọc ra là `null`.** Với `HashMap`, phải kiểm tra `containsKey` nếu cần phân biệt “khóa chưa có” và “khóa có giá trị `null`”. Cách `null` được biểu diễn trong bảng không liên quan đến quyết định này.

**Tình huống E — mất khóa sau khi đổi ID.** Đầu tiên xem khóa có trường mutable tham gia `equals/hashCode` hay không. Khắc phục ở thiết kế khóa và vòng đời của nó; không sửa ứng dụng bằng cách giả định công thức chọn bucket.

**Tình huống F — tối ưu bảng băm.** Dữ liệu phân bố hash kém có thể tăng collision và làm giảm hiệu năng. Điều chỉnh lựa chọn khóa, hàm băm và dung lượng khi có đo đạc thực tế; không dùng chi tiết treeify/resize của riêng một bản JDK như điều kiện logic để nghiệp vụ đúng.

## 11. Ghi nhớ

- Hợp đồng cho biết **kết quả và ngữ nghĩa công khai**; triển khai giải thích **cách thực hiện**, có thể thay đổi.
- `equals` xác định bình đẳng logic, `hashCode` hỗ trợ tổ chức tra cứu. **Bằng nhau ⇒ cùng mã băm**; **cùng mã băm ⇏ bằng nhau**.
- `HashMap` không bảo đảm thứ tự duyệt; `LinkedHashMap` và `TreeMap` có các cam kết thứ tự khác nhau.
- Collision không có nghĩa hai khóa bị coi là một; `HashMap` và `HashSet` vẫn phải thực hiện đúng hành vi cho các khóa khác nhau.
- Initial capacity/load factor là khái niệm và tùy chọn cấu hình được `HashMap` công bố, còn ngưỡng node/cây, công thức bucket và trình tự kiểm tra nội bộ không phải hợp đồng của `Map`.
- Đừng sửa các trường tham gia `equals/hashCode` khi đối tượng đang làm khóa trong bảng băm.
- Đọc Javadoc để xác định điều ứng dụng **được phép tin cậy**, đọc source/benchmark để hiểu và tối ưu **triển khai cụ thể**.
