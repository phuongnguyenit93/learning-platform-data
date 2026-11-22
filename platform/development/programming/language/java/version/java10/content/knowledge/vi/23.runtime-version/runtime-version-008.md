# Runtime.Version: `equals`, `equalsIgnoreOptional` và `hashCode` trong Java 10+

## 1. Mục tiêu và nguyên tắc cốt lõi

Khi Java cần xác định **hai phiên bản runtime có phải cùng một phiên bản hay không**, `java.lang.Runtime.Version` cung cấp hai định nghĩa “bằng nhau” khác nhau:

1. **`equals(Object)`**: hai phiên bản bằng nhau khi chúng đại diện **cùng phiên bản đầy đủ**, bao gồm **thông tin tùy chọn `OPT`**.
2. **`equalsIgnoreOptional(Object)`**: so sánh phiên bản **bỏ qua duy nhất phần thông tin nhận diện build tùy chọn `OPT`**; các phần khác vẫn phải tương đương.

`hashCode()` là **hàm băm chuẩn của đối tượng**, tương ứng với hợp đồng `equals(Object)`. **Không có `hashCodeIgnoreOptional()` trong API `Runtime.Version`**. Điều này đặc biệt quan trọng khi dùng phiên bản làm khóa `HashMap` hoặc phần tử `HashSet`.

Ví dụ trực quan:

~~~java
Runtime.Version a = Runtime.Version.parse("21.0.2+13-LTS");
Runtime.Version b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equals(b));               // false
System.out.println(a.equalsIgnoreOptional(b)); // true
~~~

`a` và `b` có cùng các thành phần phần số `21.0.2` và BUILD `13`, nhưng `OPT` lần lượt là `LTS` và `vendor`:

~~~text
21.0.2+13-LTS
│     │  └──── OPT = LTS
│     └─────── BUILD = 13
└───────────── VNUM = 21.0.2

21.0.2+13-vendor
│     │  └──── OPT = vendor
│     └─────── BUILD = 13
└───────────── VNUM = 21.0.2
~~~

**Kết luận:** `equalsIgnoreOptional` **không phải** phép so sánh lỏng lẻo “chỉ so số Java chính”. Nó **vẫn xét các thành phần số phiên bản, PRE và BUILD**. Chỉ OPT bị bỏ qua.

`Runtime.Version` được đưa vào Java 9, còn mô hình phiên bản phát hành theo thời gian và các tên thành phần `FEATURE/INTERIM/UPDATE/PATCH` được xác lập trong Java 10 theo **JEP 322**. Những phương thức `equals`, `equalsIgnoreOptional`, `hashCode` và các phương thức so sánh tương ứng **vẫn là API hiện hành**.

## 2. Nhắc nhanh cấu trúc phiên bản — đặc biệt là `OPT`

Một version string chuẩn được `Runtime.Version.parse` chấp nhận có phần số `VNUM`, sau đó tùy chọn thêm `PRE`, `BUILD` và `OPT`. Cú pháp có những dạng sau:

~~~text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `VNUM` | `21.0.2` | Các thành phần số của phiên bản |
| `PRE` | `ea` trong `21-ea+13` | Nhãn tiền phát hành |
| `BUILD` | `13` trong `21+13` | Số bản dựng |
| `OPT` | `LTS` trong `21+13-LTS` | Thông tin nhận diện build bổ sung |

Một số trường hợp phân biệt cần thuộc:

~~~text
21-ea        → PRE=ea, BUILD vắng mặt, OPT vắng mặt
21+-ea       → PRE vắng mặt, BUILD vắng mặt, OPT=ea
21+13        → PRE vắng mặt, BUILD=13, OPT vắng mặt
21+13-LTS    → PRE vắng mặt, BUILD=13, OPT=LTS
21-ea+13     → PRE=ea, BUILD=13, OPT vắng mặt
~~~

Không thể chỉ tách chuỗi theo dấu `-` rồi kết luận nhãn phía sau là PRE, vì `-LTS` sau BUILD lại là OPT. API đã có các getter chuẩn:

~~~java
Runtime.Version version =
        Runtime.Version.parse("21.0.2-ea+13-LTS");

System.out.println(version.version());              // [21, 0, 2]
System.out.println(version.pre().orElse("<none>"));  // ea
System.out.println(version.build().orElse(-1));      // 13
System.out.println(version.optional().orElse("?"));  // LTS
~~~

`pre()` và `optional()` trả `Optional<String>`; `build()` trả `Optional<Integer>`; `version()` trả `List<Integer>` không sửa được. Nếu không có thành phần, `Optional` rỗng — **khác với việc có BUILD=0**.

Bản thân nhãn OPT như `LTS` là **metadata của chuỗi phiên bản**; `equalsIgnoreOptional` bỏ qua nhãn này cho mục đích so sánh, nhưng không chứng minh hai nhà cung cấp JDK có bản vá, giấy phép, cam kết hỗ trợ hay chất lượng tương đương.

## 3. `equals(Object)` — tính bằng nhau đầy đủ

Chữ ký:

~~~java
public boolean equals(Object obj)
~~~

Hai `Runtime.Version` bằng nhau theo `equals` khi đại diện **cùng version string theo mô hình của `Runtime.Version`**. Điều đó bao gồm những thành phần đã được parser nhận diện, **kể cả `OPT`**.

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var same = Runtime.Version.parse("21.0.2+13-LTS");
var otherOptional = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equals(same));          // true
System.out.println(a.equals(otherOptional)); // false
~~~

**Không phải so tham chiếu:** `a` và `same` được tạo bằng hai lời gọi `parse` riêng, nhưng vẫn **bằng nhau về giá trị**.

Không viết `a == same` để xác định chúng cùng phiên bản. `Runtime.Version` là **value-based class**; dùng reference equality `==`, `System.identityHashCode(...)` hoặc monitor synchronization dựa trên identity là cách làm nên tránh. Giá trị được so bằng `equals`.

### `equals(null)` và đối tượng sai kiểu

~~~java
var v = Runtime.Version.parse("21+13-LTS");

System.out.println(v.equals(null));          // false
System.out.println(v.equals("21+13-LTS"));   // false
~~~

`String` chứa cùng chữ không phải một `Runtime.Version`. Hãy gọi `Runtime.Version.parse(...)` khi muốn chuyển **chuỗi phiên bản hợp lệ** thành đối tượng, rồi mới so sánh với một `Runtime.Version` khác.

### Không nhầm với `toString()` hoặc chuẩn hóa một tên sản phẩm

`Runtime.Version.toString()` trả chuỗi phiên bản được đại diện. Nó **không** chứa tất cả metadata về nhà cung cấp, tên JVM, tên OS, đường dẫn cài đặt, chính sách patch hoặc thông tin bản phân phối.

Nếu hai chuỗi có OPT khác nhau, `equals` phân biệt chúng theo thông tin version string. Nhưng **`equals` không phải phép kiểm tra hai runtime có cùng binary hay cùng bảo mật**; muốn xác minh các điều kiện đó cần thông tin khác ngoài phiên bản.

## 4. `equalsIgnoreOptional(Object)` — chỉ bỏ qua `OPT`

Chữ ký:

~~~java
public boolean equalsIgnoreOptional(Object obj)
~~~

Phương thức giữ nguyên kiểm tra kiểu đối tượng và so sánh các thành phần phiên bản, nhưng **bỏ qua thông tin build tùy chọn `OPT`**.

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");
var noOptional = Runtime.Version.parse("21.0.2+13");

System.out.println(a.equalsIgnoreOptional(b));          // true
System.out.println(a.equalsIgnoreOptional(noOptional)); // true
~~~

Trong cả hai phép so sánh trên, **VNUM, PRE và BUILD đều giống nhau**; chỉ OPT thay đổi hoặc bị bỏ hẳn.

### Những gì `equalsIgnoreOptional` KHÔNG bỏ qua

**1. Không bỏ qua BUILD**

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+14-vendor");

System.out.println(a.equalsIgnoreOptional(b)); // false
~~~

`13` và `14` là hai BUILD khác nhau. `IgnoreOptional` không biến thành “ignore build”.

**2. Không bỏ qua PRE**

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2-ea+13-LTS");

System.out.println(a.equalsIgnoreOptional(b)); // false
~~~

`b` có PRE `ea`, còn `a` không có PRE, nên chúng không tương đương theo cách bỏ OPT.

**3. Không bỏ qua phần số VNUM**

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.3+13-vendor");

System.out.println(a.equalsIgnoreOptional(b)); // false
~~~

`UPDATE` khác nhau giữa `21.0.2` và `21.0.3`, nên bỏ OPT cũng không giúp hai phiên bản bằng nhau.

**4. Không biến input `null` hoặc sai kiểu thành phiên bản hợp lệ**

~~~java
var v = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(v.equalsIgnoreOptional(null)); // false
System.out.println(
        v.equalsIgnoreOptional("21.0.2+13-LTS"));  // false
~~~

Giống `equals`, phương thức yêu cầu đối tượng còn lại là `Runtime.Version` để so. Khi đối số là kiểu khác, không có quá trình parse chuỗi tự động.

### Khi nào nên bỏ OPT?

Hữu ích khi hỏi: “Hai build có **cùng số phiên bản, PRE và BUILD**, nhưng nhãn bổ sung có khác không quan trọng đối với bài toán này?”

Ví dụ:

- Gộp những dòng log có cùng `21.0.2+13` nhưng nhãn build `LTS`, `vendor` khác nhau, **nếu ứng dụng chủ động chọn bỏ qua OPT**.
- So bản runtime ở mức VNUM/PRE/BUILD khi chính sách chỉ yêu cầu những thành phần này.
- Tổ chức báo cáo tương đương theo một “version core”, không tính chuỗi nhận diện tùy chọn.

Không nên bỏ OPT khi chính thông tin nhận diện nhà phân phối là tiêu chí bắt buộc để phân biệt gói hoặc điều tra lỗi. Và **không nên kết luận hai bản build thực sự giống byte-for-byte** chỉ từ kết quả `equalsIgnoreOptional=true`.

## 5. Bảng so sánh các trường hợp

Giả sử `a` là `21.0.2+13-LTS`:

| Đối tượng `b` | `a.equals(b)` | `a.equalsIgnoreOptional(b)` | Lý do |
| --- | --- | --- | --- |
| `21.0.2+13-LTS` | `true` | `true` | Mọi thành phần trùng |
| `21.0.2+13-vendor` | `false` | `true` | Chỉ khác OPT |
| `21.0.2+13` | `false` | `true` | Chỉ thiếu OPT |
| `21.0.2+14-LTS` | `false` | `false` | BUILD khác |
| `21.0.2-ea+13-LTS` | `false` | `false` | PRE khác |
| `21.0.3+13-LTS` | `false` | `false` | VNUM khác |
| `null` | `false` | `false` | Không phải Version |
| `"21.0.2+13-LTS"` kiểu String | `false` | `false` | Sai kiểu đối tượng |

Bảng cho thấy rõ quan hệ: **`a.equals(b) == true` luôn kéo theo `a.equalsIgnoreOptional(b) == true`**. Chiều ngược lại **không đúng**, vì hai chuỗi có thể khác OPT.

Khi ứng dụng chuyển từ so sánh đầy đủ sang bỏ OPT, nó **nới nhóm tương đương** bằng cách gộp các nhãn tùy chọn; không được tự gộp các phiên bản khác BUILD/PRE/VNUM.

## 6. `hashCode()` — hợp đồng của `equals`, KHÔNG phải `equalsIgnoreOptional`

Chữ ký:

~~~java
public int hashCode()
~~~

`Runtime.Version.hashCode()` trả về một giá trị băm phục vụ các cấu trúc như `HashMap` và `HashSet`. Hợp đồng Java `Object.hashCode` quy định:

> Nếu hai đối tượng bằng nhau theo `equals(Object)`, chúng phải có cùng hash code trong cùng lần thực thi.

Các điều **không** được suy luận:

- Hai phiên bản **khác nhau theo `equals`** không bắt buộc phải có hash code khác nhau; **hash collision** là điều có thể xảy ra.
- Hai phiên bản **bằng nhau theo `equalsIgnoreOptional`** không được bảo đảm có hash code bằng nhau từ hợp đồng `equalsIgnoreOptional`.
- Không có phương thức `Runtime.Version.hashCodeIgnoreOptional()` trong API hiện hành.
- Giá trị số cụ thể của `hashCode()` không phải một mã phiên bản, không nên lưu để trao đổi giữa hệ thống hoặc cố định trong test xuyên JDK.
- `hashCode()` **không phải** hàm băm mật mã; không dùng để xác thực tính toàn vẹn của file JDK, chữ ký số hay bản build.

### Kiểm tra hợp đồng đúng cách

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var same = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(a.equals(same)); // true
System.out.println(
        a.hashCode() == same.hashCode()); // true
~~~

Hai lời gọi `parse` có thể tạo hai đối tượng, nhưng `equals` là `true` nên hash code **phải** giống nhau. Đó là bất biến đáng dùng để kiểm thử.

### Trường hợp bỏ OPT

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equalsIgnoreOptional(b)); // true
System.out.println(a.equals(b));               // false
~~~

Ở đây **không được** khẳng định:

~~~java
// Không có hợp đồng nào bảo đảm:
// a.hashCode() == b.hashCode()
// Chỉ vì a.equalsIgnoreOptional(b) == true.
~~~

Khi dùng băm, `HashMap` và `HashSet` áp dụng hợp đồng **`equals`**, không áp dụng một phương thức so sánh thay thế như `equalsIgnoreOptional`. Nếu muốn băm theo “bỏ OPT”, phải tạo **khóa chuẩn hóa có `equals/hashCode` riêng** hoặc chọn cấu trúc dữ liệu hỗ trợ một chiến lược so sánh phù hợp.

### Không đồng nhất hash với identity

`Runtime.Version` là **value-based**. `System.identityHashCode(v)` hay `v == other` phản ánh khía cạnh identity mà người dùng lớp này được khuyên không dựa vào. `v.hashCode()` là hàm băm của **giá trị theo `equals`**, không phải công cụ xác định hai biến tham chiếu cùng một instance.

## 7. Hệ quả với `HashSet` và `HashMap`

### `HashSet<Runtime.Version>` giữ hai phiên bản chỉ khác OPT thành hai phần tử

~~~java
import java.util.HashSet;
import java.util.Set;

var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

Set<Runtime.Version> versions = new HashSet<>();
versions.add(a);
versions.add(b);

System.out.println(versions.size()); // 2
~~~

Tại sao bằng 2?

`HashSet` dùng `hashCode` và `equals` để xác định phần tử trùng. Do `a.equals(b)` là `false`, chúng là **hai giá trị khác nhau** với `HashSet`, dù `a.equalsIgnoreOptional(b)` là `true`.

Không có việc `HashSet` tự “nhìn thấy” phương thức `equalsIgnoreOptional` rồi chọn dùng nó.

### `contains` vẫn kiểm tra theo `equals`

~~~java
Set<Runtime.Version> set = new HashSet<>();
set.add(a);

System.out.println(set.contains(b)); // false
~~~

Nếu ứng dụng cần một quan hệ bằng nhau không tính OPT, câu lệnh trên **không thực hiện** ý định đó.

### `HashMap<Runtime.Version, Value>` cũng phân biệt OPT

~~~java
import java.util.HashMap;
import java.util.Map;

Map<Runtime.Version, String> notes = new HashMap<>();
notes.put(a, "first");

System.out.println(notes.get(b)); // null
~~~

`notes.get(b)` là `null` vì `b` không bằng `a` theo `equals`, và chỉ có một mục với khóa `a`. Không phải do `HashMap` “chưa hỗ trợ Java 10”; đó là hợp đồng chung của `Map` dựa trên khóa.

**Đừng chọn cách cố ép hai đối tượng phiên bản có hash code giống nhau** bằng thủ thuật. Hash code trùng không khiến `equals` thành true; map vẫn có thể giữ hai khóa khác nhau trong cùng bucket.

## 8. So sánh tự nhiên và so sánh bỏ `OPT`

`Runtime.Version` triển khai `Comparable<Runtime.Version>`. Nó có hai cách sắp xếp:

~~~java
int full = a.compareTo(b);
int ignoringOpt = a.compareToIgnoreOptional(b);
~~~

Theo tài liệu:

- `compareTo` xét lần lượt **VNUM → PRE → BUILD → OPT**.
- `compareToIgnoreOptional` xét tương tự nhưng **bỏ OPT**.

Tính nhất quán rất quan trọng:

~~~text
a.compareTo(b) == 0
     ↔ a.equals(b)

a.compareToIgnoreOptional(b) == 0
     ↔ a.equalsIgnoreOptional(b)
~~~

Đây là lý do Javadoc khuyên **dùng phương thức so sánh đúng cặp với phương thức bằng nhau tương ứng**.

Ví dụ:

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.compareTo(b) != 0);              // true
System.out.println(a.compareToIgnoreOptional(b) == 0); // true
~~~

Không nên trộn một phép kiểm tra “đã bằng nhau” theo `equalsIgnoreOptional` với một thuật toán sắp xếp theo `compareTo` rồi kỳ vọng cùng quy tắc chia nhóm.

### Không nhầm `compareToIgnoreOptional` với chỉ so FEATURE

Hai phiên bản có FEATURE giống nhau, nhưng khác BUILD, vẫn khác theo `compareToIgnoreOptional`:

~~~java
var b13 = Runtime.Version.parse("21.0.2+13-LTS");
var b14 = Runtime.Version.parse("21.0.2+14-vendor");

System.out.println(
        b13.compareToIgnoreOptional(b14) < 0); // true
~~~

Nếu nghiệp vụ chỉ quan tâm tính tương thích **theo FEATURE**, hãy dùng `feature()` hoặc chính sách phù hợp. Đừng diễn đạt “bỏ OPT” như “bỏ hết metadata build”.

## 9. `TreeSet` với Comparator bỏ `OPT`: tiện nhưng phải biết giới hạn

`TreeSet` dùng thứ tự của comparator để quyết định **hai phần tử có cùng khóa sắp xếp** hay không. Có thể truyền:

~~~java
import java.util.TreeSet;

TreeSet<Runtime.Version> versions =
        new TreeSet<>(Runtime.Version::compareToIgnoreOptional);

var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

versions.add(a);
versions.add(b);

System.out.println(versions.size()); // 1
System.out.println(versions.contains(b)); // true
~~~

`compareToIgnoreOptional(a,b) == 0`, nên TreeSet coi hai giá trị là cùng một vị trí trong cấu trúc sắp xếp và chỉ giữ một đại diện. **Không có nghĩa `a.equals(b)` đổi thành true**, và cũng không làm thay đổi `hashCode`.

**Cảnh báo về hợp đồng `Set`:** Java Collections Framework khuyến nghị comparator dùng cho sorted sets **nhất quán với `equals`**. Comparator bỏ OPT **không nhất quán** với `Runtime.Version.equals`, nên `TreeSet` này có thể hoạt động theo thứ tự sắp xếp được mong muốn nhưng không còn tuân thủ đầy đủ hợp đồng `Set` dựa trên `equals`. Những thao tác khi tương tác với collections khác, kiểm tra equality hoặc chuyển đổi cấu trúc có thể gây bất ngờ.

Vì thế, nếu ứng dụng thực sự cần **một nhóm bản build bỏ OPT** và muốn dùng `HashSet`/`HashMap` chuẩn, tốt hơn là tạo **kiểu khóa chuẩn hóa** riêng như phần tiếp theo. Dùng comparator bỏ OPT chủ yếu khi đã hiểu rõ và chấp nhận ngữ nghĩa nhất quán theo comparator, không coi nó như thay thế tổng quát cho `equals`.

### `TreeMap` tương tự

`TreeMap` cũng phân biệt các khóa dựa trên comparator. Với comparator bỏ OPT, `put(a, value1)` rồi `put(b, value2)` có thể cập nhật giá trị tại cùng một vị trí so sánh, thay vì tạo hai mục. Nếu cần vừa giữ cả hai phiên bản chính xác vừa biết chúng cùng “version core”, hãy lưu cấu trúc dữ liệu phản ánh cả hai lớp định danh.

## 10. Giải pháp cho HashMap/HashSet khi cần bỏ OPT: kiểu khóa chuẩn hóa

Nếu nghiệp vụ muốn các phiên bản bằng nhau khi **VNUM, PRE và BUILD giống nhau** bất kể OPT, hãy xác định một kiểu **key** mà `equals/hashCode` của nó cũng bỏ OPT.

Với Java 17+ có thể dùng `record` để có `equals` và `hashCode` tự động, bao gồm chính xác những field được khai báo:

~~~java
import java.util.List;

record CoreVersion(
        List<Integer> numbers,
        String pre,
        Integer build) {

    static CoreVersion of(Runtime.Version v) {
        return new CoreVersion(
                List.copyOf(v.version()),
                v.pre().orElse(null),
                v.build().orElse(null));
    }
}
~~~

**Đây là một khai báo `record` minh họa**, không có `main` độc lập. `record` là tính năng chuẩn được đưa vào Java 16, nên ví dụ yêu cầu **JDK 17+**; các phương thức `Runtime.Version` đang học vẫn thuộc API Java 10+.

Các trường khóa:

1. `numbers`: danh sách `VNUM` gồm các thành phần số.
2. `pre`: nhãn PRE hoặc `null` nếu không có.
3. `build`: BUILD hoặc `null` nếu không có — **phân biệt với BUILD=0**.

**Không khai báo OPT**, nên record tự động so sánh/băm trên các thành phần **không bao gồm OPT**. `List.copyOf(v.version())` tạo danh sách số không sửa được; `version()` cũng trả danh sách unmodifiable, nhưng copy phòng vệ làm ý định của khóa rõ ràng.

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(CoreVersion.of(a).equals(CoreVersion.of(b)));
// true
~~~

### HashSet dùng CoreVersion

~~~java
var keys = new java.util.HashSet<CoreVersion>();

keys.add(CoreVersion.of(a));
keys.add(CoreVersion.of(b));

System.out.println(keys.size()); // 1
~~~

Lúc này `HashSet` dùng `CoreVersion.equals` và `CoreVersion.hashCode` sinh từ các trường record. Cả hai đều **cùng bỏ qua OPT** vì kiểu khóa không có trường này, nên hợp đồng băm và bằng nhau **nhất quán**.

Đây là sự khác biệt quan trọng so với việc dùng trực tiếp `Runtime.Version` làm khóa rồi cố xử lý bằng `equalsIgnoreOptional` bên ngoài.

### Trường hợp không có BUILD và BUILD=0

~~~java
var absent = CoreVersion.of(Runtime.Version.parse("21"));
var zero = CoreVersion.of(Runtime.Version.parse("21+0"));

System.out.println(absent.equals(zero)); // false
~~~

Ở đây `build=null` và `build=0` khác nhau. Điều đó phù hợp với ý định “bỏ OPT nhưng giữ BUILD”. Nếu dùng `v.build().orElse(0)` khi tạo khóa thì sẽ **vô tình gộp** hai trường hợp khác nhau.

### Cẩn thận với record mutable component

Trong `CoreVersion`, các trường là `List<Integer>` không sửa được, `String` và `Integer` bất biến. Nó phù hợp làm khóa băm. Với những record khác có component kiểu mutable như `ArrayList`, chỉ vì là record chưa đủ để bảo đảm trạng thái không đổi; cần copy phòng vệ và thiết kế hợp đồng `equals/hashCode` đúng.

## 11. Chương trình Java hoàn chỉnh, runnable và có stdout xác định

Lưu tệp **`VersionEqualityDemo.java`** và biên dịch bằng **JDK 17+**. Chương trình dùng `record` để minh họa khóa chuẩn hóa; toàn bộ API `Runtime.Version` được sử dụng đã có trong Java 10 hoặc trước đó.

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class VersionEqualityDemo {

    record Core(List<Integer> nums, String pre, Integer build) {
        static Core of(Runtime.Version v) {
            return new Core(
                    List.copyOf(v.version()),
                    v.pre().orElse(null),
                    v.build().orElse(null));
        }
    }

    public static void main(String[] args) {
        Runtime.Version a =
                Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version b =
                Runtime.Version.parse("21.0.2+13-vendor");
        Runtime.Version same =
                Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version noOpt =
                Runtime.Version.parse("21.0.2+13");
        Runtime.Version differentBuild =
                Runtime.Version.parse("21.0.2+14-LTS");
        Runtime.Version early =
                Runtime.Version.parse("21.0.2-ea+13-LTS");

        System.out.println("a=" + a);
        System.out.println("aEqualsB=" + a.equals(b));
        System.out.println(
                "aIgnoreOptB=" + a.equalsIgnoreOptional(b));
        System.out.println(
                "aEqualsSame=" + a.equals(same));

        System.out.println(
                "sameHashForEqual="
                + (a.hashCode() == same.hashCode()));
        System.out.println(
                "stableHash=" + (a.hashCode() == a.hashCode()));

        System.out.println("aEqualsNull=" + a.equals(null));
        System.out.println(
                "ignoreOptNull=" + a.equalsIgnoreOptional(null));
        System.out.println(
                "aEqualsString=" + a.equals("21.0.2+13-LTS"));
        System.out.println(
                "ignoreOptString="
                + a.equalsIgnoreOptional("21.0.2+13-LTS"));

        System.out.println(
                "strictCompareNonZero=" + (a.compareTo(b) != 0));
        System.out.println(
                "ignoreOptCompareZero="
                + (a.compareToIgnoreOptional(b) == 0));

        System.out.println(
                "ignoreOptNoOpt=" + a.equalsIgnoreOptional(noOpt));
        System.out.println(
                "strictNoOpt=" + a.equals(noOpt));
        System.out.println(
                "ignoreOptOtherBuild="
                + a.equalsIgnoreOptional(differentBuild));
        System.out.println(
                "ignoreOptEarly=" + a.equalsIgnoreOptional(early));

        var versions = new HashSet<Runtime.Version>(
                List.of(a, b));

        System.out.println("hashSetSize=" + versions.size());

        var onlyA = new HashSet<Runtime.Version>(
                List.of(a));

        System.out.println(
                "hashSetLookupOtherOpt=" + onlyA.contains(b));

        var cache = new HashMap<Runtime.Version, String>();
        cache.put(a, "first");

        System.out.println(
                "mapLookupOtherOpt=" + cache.get(b));

        var strictSorted = new TreeSet<Runtime.Version>();
        strictSorted.add(a);
        strictSorted.add(b);

        System.out.println(
                "treeSetStrictSize=" + strictSorted.size());

        var ignoreSorted = new TreeSet<Runtime.Version>(
                Runtime.Version::compareToIgnoreOptional);

        ignoreSorted.add(a);
        ignoreSorted.add(b);

        System.out.println(
                "treeSetIgnoreSize=" + ignoreSorted.size());
        System.out.println(
                "treeSetIgnoreContainsB=" + ignoreSorted.contains(b));

        var keys = new HashSet<Core>();
        keys.add(Core.of(a));
        keys.add(Core.of(b));

        System.out.println(
                "coreKeysEqual=" + Core.of(a).equals(Core.of(b)));
        System.out.println(
                "coreKeySetSize=" + keys.size());
        System.out.println(
                "coreDiffBuild="
                + !Core.of(a).equals(Core.of(differentBuild)));
    }
}
~~~

Chạy:

~~~bash
javac VersionEqualityDemo.java
java VersionEqualityDemo
~~~

**`stdout` đã được đối chiếu trên JDK 24:**

~~~text
a=21.0.2+13-LTS
aEqualsB=false
aIgnoreOptB=true
aEqualsSame=true
sameHashForEqual=true
stableHash=true
aEqualsNull=false
ignoreOptNull=false
aEqualsString=false
ignoreOptString=false
strictCompareNonZero=true
ignoreOptCompareZero=true
ignoreOptNoOpt=true
strictNoOpt=false
ignoreOptOtherBuild=false
ignoreOptEarly=false
hashSetSize=2
hashSetLookupOtherOpt=false
mapLookupOtherOpt=null
treeSetStrictSize=2
treeSetIgnoreSize=1
treeSetIgnoreContainsB=true
coreKeysEqual=true
coreKeySetSize=1
coreDiffBuild=true
~~~

Cách diễn giải kết quả:

1. `aEqualsB=false` nhưng `aIgnoreOptB=true` — hai bản chỉ khác OPT.
2. `aEqualsSame=true`, `sameHashForEqual=true` — cặp bằng nhau theo `equals` bắt buộc có cùng hash code.
3. `stableHash=true` — bản thử nghiệm không thay đổi thông tin giá trị trong cùng lần chạy; kiểm thử **không phụ thuộc giá trị số hash**.
4. `aEqualsNull=false` và `ignoreOptNull=false` — truyền null cho hai phương thức equality đều cho false, không tự ném NPE như một thao tác so sánh thứ tự với null.
5. `aEqualsString=false` và `ignoreOptString=false` — chuỗi String chưa parse không phải Runtime.Version.
6. `strictCompareNonZero=true` và `ignoreOptCompareZero=true` — hai phương thức so sánh thứ tự khớp hai định nghĩa equality.
7. `ignoreOptNoOpt=true` — chỉ OPT vắng mặt là được bỏ qua; `ignoreOptOtherBuild=false` và `ignoreOptEarly=false` — BUILD và PRE khác vẫn khiến không bằng.
8. `hashSetSize=2`, `hashSetLookupOtherOpt=false` và `mapLookupOtherOpt=null` — các collections băm chuẩn dùng `equals/hashCode`, không dùng `equalsIgnoreOptional`.
9. `treeSetStrictSize=2`, `treeSetIgnoreSize=1` — comparator thay đổi quan hệ “cùng vị trí sắp xếp”; lưu ý cảnh báo về comparator không nhất quán với `equals`.
10. `coreKeysEqual=true` và `coreKeySetSize=1` — kiểu khóa `record Core` bỏ OPT **trong cả equality lẫn hashCode**, nên phù hợp hơn khi muốn băm theo version core.

Chương trình chỉ phân tích những chuỗi phiên bản cố định, vì vậy output không phụ thuộc vào số Java feature của runtime đang chạy. Không in giá trị hash nguyên dạng hay ký hiệu build của runtime cài đặt để tránh phụ thuộc chi tiết triển khai.

## 12. Xử lý Null, phiên bản không hợp lệ và ngoại lệ

### `equals` / `equalsIgnoreOptional` nhận `Object`

Hai phương thức đều nhận `Object`:

~~~java
boolean e1 = a.equals(null);               // false
boolean e2 = a.equalsIgnoreOptional(null); // false
~~~

Đừng nhầm với hai phương thức so sánh thứ tự:

~~~java
// Các lời gọi sau có thể ném NullPointerException:
a.compareTo(null);
a.compareToIgnoreOptional(null);
~~~

Hãy xử lý null sớm khi xây dựng chính sách so sánh:

~~~java
if (candidate == null) {
    // Từ chối, bỏ qua hoặc xử lý theo hợp đồng nghiệp vụ.
}
~~~

### `Runtime.Version.parse` nhận chuỗi hợp lệ

~~~java
Runtime.Version good = Runtime.Version.parse(
        "21.0.2+13-LTS");
~~~

Khi input không hợp lệ, `Runtime.Version.parse` có thể ném `IllegalArgumentException` (và một số subclass như `NumberFormatException` khi số vượt giới hạn). Đối số parse null ném `NullPointerException`.

~~~java
try {
    Runtime.Version parsed =
            Runtime.Version.parse(userInput);
    // Chỉ so sánh sau khi đã parse thành công.
} catch (IllegalArgumentException ex) {
    // Dữ liệu phiên bản không hợp lệ: xử lý theo nghiệp vụ.
}
~~~

Đây là **đoạn mã minh họa trong một phương thức**, với `userInput` là chuỗi đầu vào do ứng dụng cung cấp. Nếu `userInput` có thể null, cần kiểm tra hoặc xử lý `NullPointerException` riêng.

**Không tự parse một dòng dài của lệnh `java --version`** bằng `Runtime.Version.parse`: dòng thông báo có thể chứa tên JVM, nhà sản xuất, số build và nhiều chữ khác không thuộc ngữ pháp version string. Khi cần phiên bản của runtime đang chạy, dùng `Runtime.version()`.

### Không nhầm hiện hành với cách đặt tên cũ

Từ Java 10, nên dùng `feature()`, `interim()`, `update()` và `patch()` cho các thành phần số. Tránh các accessor `major()`, `minor()`, `security()` đã được đánh dấu deprecated từ Java 10. Việc chọn `equalsIgnoreOptional` **không** thay thế các kiểm tra tương thích hoặc mức cập nhật bảo mật.

## 13. Hợp đồng bằng nhau và những kiểm thử nên viết

Một bài kiểm thử tốt phải phân biệt **hai định nghĩa equality** và không dùng hash code như mã định danh chính xác.

### Kiểm thử giá trị bằng nhau đầy đủ

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var same = Runtime.Version.parse("21.0.2+13-LTS");

assert a.equals(same);
assert a.hashCode() == same.hashCode();
assert a.compareTo(same) == 0;
~~~

Lệnh `assert` trong Java chỉ được đánh giá khi bật assertion (`java -ea`); trong hệ thống test thực tế, dùng assertion của JUnit hoặc framework kiểm thử để luôn chạy.

### Kiểm thử bỏ OPT

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

assert !a.equals(b);
assert a.equalsIgnoreOptional(b);
assert a.compareToIgnoreOptional(b) == 0;
~~~

**Không thêm** vào test:

~~~java
// Không hợp lệ như một invariant API:
// assert a.hashCode() == b.hashCode();
~~~

Việc các giá trị bằng nhau theo **một phương thức tùy chọn** không bắt buộc băm giống nhau theo **hợp đồng `equals` chuẩn**.

### Kiểm thử BUILD, PRE và VNUM vẫn quan trọng

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");

assert !a.equalsIgnoreOptional(
        Runtime.Version.parse("21.0.2+14-vendor"));

assert !a.equalsIgnoreOptional(
        Runtime.Version.parse("21.0.2-ea+13-vendor"));

assert !a.equalsIgnoreOptional(
        Runtime.Version.parse("21.0.3+13-vendor"));
~~~

Những test này bảo đảm code không vô tình triển khai một “ignore-build” hay “ignore-pre-release” rộng hơn yêu cầu.

### Kiểm thử collections đúng với nghĩa của khóa

Khi dùng `HashSet<Runtime.Version>`, kỳ vọng hai phiên bản chỉ khác OPT **là hai phần tử khác nhau**. Khi dùng `HashSet<CoreVersion>`, kỳ vọng chúng được gộp nhờ `CoreVersion.equals/hashCode`. Đừng trộn kỳ vọng của hai lớp.

## 14. Kịch bản thiết kế thực tế

### Kịch bản A — kho thông tin runtime chính xác

Bài toán: muốn phân biệt **hai version string đầy đủ** nhằm ghi log, thống kê chi tiết các bản build, debug sai khác giữa các nhãn OPT.

**Giải pháp:**

~~~java
Map<Runtime.Version, String> buildNotes = new HashMap<>();
buildNotes.put(Runtime.Version.parse("21.0.2+13-LTS"), "A");
buildNotes.put(Runtime.Version.parse("21.0.2+13-vendor"), "B");
~~~

`Map` giữ hai khóa khác nhau. Đây là điều đúng khi OPT cần được phân biệt.

### Kịch bản B — nhóm phiên bản theo VNUM/PRE/BUILD

Bài toán: báo cáo cho rằng **không cần phân biệt OPT**, nhưng vẫn phải tách build 13 và 14.

**Giải pháp:** dùng `CoreVersion.of(v)` làm khóa HashMap/HashSet, như ở phần 10. `equals/hashCode` của record tự nhất quán. Khi nhóm, nên có chính sách lưu **tất cả các chuỗi phiên bản gốc** làm giá trị nếu cần truy dấu, không tự xóa mất dấu vết nhãn vendor.

### Kịch bản C — quyết định một tính năng API có được hỗ trợ không

Bài toán: chương trình cần API có từ Java 17 và chỉ cần kiểm tra **feature release**.

**Giải pháp:**

~~~java
boolean supported = Runtime.version().feature() >= 17;
~~~

`equalsIgnoreOptional` không phù hợp ở đây vì nó vẫn đòi các thành phần khác giống nhau, chẳng hạn BUILD và UPDATE. Việc dùng runtime Java 17+ cũng không tự đảm bảo môi trường có đầy đủ module, quyền truy cập hay bản cập nhật bảo mật cần thiết.

### Kịch bản D — lọc bỏ bản tiền phát hành

Bài toán: chính sách chỉ nhận runtime có chuỗi version **không mang PRE**.

~~~java
boolean noPreLabel = Runtime.version().pre().isEmpty();
~~~

Đây là một kiểm tra được xác định theo chuỗi phiên bản, không phải chứng chỉ độc lập về chất lượng hoặc trạng thái hỗ trợ của nhà phát hành. `equalsIgnoreOptional` không bỏ PRE và cũng không thay được logic chính sách phát hành này.

### Kịch bản E — sắp xếp danh sách vẫn phải giữ tất cả bản chính xác

Bài toán: muốn nhóm các bản cùng core nhưng vẫn giữ cả hai nhãn OPT.

**Giải pháp:** có thể dùng `List<Runtime.Version>` rồi sắp xếp với comparator phù hợp; comparator bằng nhau không tự loại phần tử khi sắp xếp list.

~~~java
var versions = new java.util.ArrayList<Runtime.Version>(
        java.util.List.of(a, b));

versions.sort(Runtime.Version::compareToIgnoreOptional);
// List vẫn chứa 2 phần tử dù comparator trả về 0.
~~~

Nếu sắp xếp trong `TreeSet`, comparator trả 0 có thể khiến một bản không được thêm. **Sắp xếp** và **khử trùng** là hai mục tiêu khác nhau, cần chọn cấu trúc dữ liệu theo từng mục tiêu.

## 15. Các lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`equalsIgnoreOptional` bỏ cả BUILD.” | Chỉ OPT được bỏ. | Đối chiếu VNUM/PRE/BUILD. |
| “`equalsIgnoreOptional` luôn giống `equals`.” | Khác khi OPT khác/vắng mặt. | Chọn định nghĩa bình đẳng theo bài toán. |
| “`hashCode` cũng tự bỏ OPT vì có phương thức IgnoreOptional.” | `hashCode` gắn hợp đồng `equals` chuẩn. | Muốn bỏ OPT khi băm thì dùng khóa chuẩn hóa. |
| “Hai hash khác nhau nghĩa là hai Runtime.Version khác nhau theo core.” | Hash dùng chuẩn equals; core có thể trùng dù OPT khác. | Dùng `equalsIgnoreOptional`/`CoreVersion`. |
| “Hai hash giống nhau chắc chắn equals true.” | Có thể có hash collision. | Kiểm tra `equals`. |
| “HashSet tự chọn equalsIgnoreOptional.” | HashSet dùng `equals`. | Thay kiểu key hoặc chọn cấu trúc phù hợp. |
| “Đưa comparator IgnoreOptional vào TreeSet là tương đương HashSet.” | Comparator có thể không nhất quán với equals chuẩn. | Hiểu SortedSet contract; dùng core key nếu cần. |
| “`compareToIgnoreOptional` bỏ qua hết metadata.” | Vẫn so PRE/BUILD. | Đọc đúng Javadoc. |
| “`==` so đúng hai Version.” | Runtime.Version là value-based. | Dùng `equals`. |
| “Hash code là số build hoặc fingerprint gói JDK.” | Hash code không có ngữ nghĩa định danh bảo mật. | Dùng mã version và metadata chính xác. |
| “Bỏ OPT là đủ để kết luận cùng nhà cung cấp/cùng security patch.” | OPT chỉ là thông tin thêm trong chuỗi; nhiều dữ liệu khác tồn tại. | Xác minh nhà phân phối và release notes. |
| “Hai Version chỉ cần cùng feature là bằng nhau.” | UPDATE/PATCH/PRE/BUILD/OPT có thể khác. | Dùng `feature()` riêng nếu đó là tiêu chí thật. |
| “Đối số String được equalsIgnoreOptional tự parse.” | Phương thức nhận Object, chỉ so Version. | Parse thành Runtime.Version trước. |
| “Dùng Version làm khóa synchronized an toàn.” | Lớp value-based không phù hợp identity-sensitive locking. | Dùng lock object riêng. |

## 16. Câu hỏi tự kiểm tra

### Câu 1 — chỉ khác OPT

Cho:

~~~text
a = 21.0.2+13-LTS
b = 21.0.2+13-vendor
~~~

**Hỏi:** `a.equals(b)` và `a.equalsIgnoreOptional(b)` là gì?

**Đáp án:** `false` và `true`. VNUM, PRE (cùng không có), BUILD đều giống; OPT khác.

### Câu 2 — BUILD khác

~~~text
a = 21.0.2+13-LTS
b = 21.0.2+14-LTS
~~~

**Hỏi:** `equalsIgnoreOptional` trả true không?

**Đáp án:** **Không**, vì BUILD khác nhau. Nó không có chức năng bỏ BUILD.

### Câu 3 — PRE khác

~~~text
a = 21.0.2+13-LTS
b = 21.0.2-ea+13-LTS
~~~

**Đáp án:** `equalsIgnoreOptional` trả `false` vì một bên có `PRE=ea`.

### Câu 4 — hợp đồng hash

Hai `Runtime.Version` đều parse từ `"21+13-LTS"` và `equals` trả true. Chúng có bắt buộc cùng `hashCode` không?

**Đáp án:** **Có**. Hợp đồng `Object.hashCode` yêu cầu đối tượng bằng nhau theo `equals` có cùng giá trị băm.

### Câu 5 — bỏ OPT và băm

Hai phiên bản chỉ khác OPT có `equalsIgnoreOptional=true`. Có được suy ra `hashCode` của hai phiên bản bằng nhau không?

**Đáp án:** **Không**. Không có hợp đồng `hashCodeIgnoreOptional`, nên muốn băm theo lõi phiên bản phải dùng khóa chuẩn hóa có `equals/hashCode` thống nhất.

### Câu 6 — HashSet

Cho `HashSet<Runtime.Version>`, thêm `a=21+13-LTS` và `b=21+13-vendor`. Kích thước là bao nhiêu?

**Đáp án:** **2**, vì `equals` chuẩn phân biệt OPT.

### Câu 7 — TreeSet

Dùng `new TreeSet<>(Runtime.Version::compareToIgnoreOptional)` rồi thêm hai bản chỉ khác OPT. Kích thước có thể là bao nhiêu theo comparator?

**Đáp án:** **1**, vì comparator trả 0; tuy nhiên comparator không nhất quán với `equals` chuẩn của `Runtime.Version` nên cần hiểu giới hạn về hợp đồng `Set`.

### Câu 8 — khóa băm đúng

Một ứng dụng muốn coi các bản chỉ khác OPT là cùng khóa HashMap. Có nên chỉ gọi `equalsIgnoreOptional` trong code xử lý khi vẫn lưu khóa `Runtime.Version` không?

**Đáp án:** **Không đủ**. HashMap không dùng phép so sánh tùy chọn đó. Hãy dùng một kiểu khóa với các trường VNUM, PRE, BUILD và `equals/hashCode` phù hợp, hoặc mô hình nhóm dữ liệu khác.

### Câu 9 — không có OPT so với có OPT

~~~java
var a = Runtime.Version.parse("21+13");
var b = Runtime.Version.parse("21+13-LTS");
~~~

**Đáp án:** `a.equals(b) == false`, `a.equalsIgnoreOptional(b) == true`.

### Câu 10 — phân biệt giá trị và identity

Nếu `a` và `b` đều parse từ cùng chuỗi, có nên kiểm tra `a == b` không?

**Đáp án:** Không. `Runtime.Version` là value-based class; dùng `equals` để đánh giá giá trị, không dựa vào identity.

## 17. Kết luận và nguồn tham khảo

- `Runtime.Version.equals(Object)` so sánh **đầy đủ version string**, bao gồm OPT.
- `Runtime.Version.equalsIgnoreOptional(Object)` bỏ qua **duy nhất OPT**; VNUM, PRE và BUILD vẫn phải tương đương.
- `Runtime.Version.hashCode()` phục vụ hợp đồng **`equals(Object)`**, không phải một phiên bản băm bỏ OPT. **Cùng equals ⇒ cùng hash**, nhưng **cùng hash ⇏ cùng equals**.
- Với `HashSet` và `HashMap`, dùng `Runtime.Version` làm key thì **các phiên bản chỉ khác OPT vẫn được phân biệt**.
- `compareTo` nhất quán với `equals`; `compareToIgnoreOptional` nhất quán với `equalsIgnoreOptional`. `TreeSet` dùng comparator bỏ OPT sẽ gộp khóa so sánh, nhưng comparator đó không nhất quán với `Runtime.Version.equals` theo hợp đồng Set.
- Khi thực sự cần **hash theo lõi phiên bản không tính OPT**, dùng **kiểu khóa chuẩn hóa** có `equals/hashCode` nhất quán (ví dụ record Java 17+ với VNUM, PRE, BUILD).
- Tránh so sánh identity `==` hoặc đồng bộ trên `Runtime.Version` vì đây là **value-based class**.
- Việc hai phiên bản bằng nhau/bỏ OPT khi so sánh **không phải** chứng minh chúng cùng bản vá, binary hoặc chính sách hỗ trợ.

### Nguồn chính thức (còn hiệu lực)

1. [Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): `equals`, `equalsIgnoreOptional`, `hashCode`, `compareTo`, `compareToIgnoreOptional` và định nghĩa thành phần phiên bản.
2. [Java SE 26 — `Object.hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#hashCode()): hợp đồng bằng nhau/băm và hash collision.
3. [Java SE 26 — `HashSet` và `HashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HashSet.html): collection băm dùng `equals`/`hashCode` chuẩn.
4. [Java SE 26 — `TreeSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html): comparator, điều kiện nhất quán với equals và SortedSet contract.
5. [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình phiên bản từ Java 10 và thành phần BUILD/OPT.
