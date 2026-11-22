# Thành phần tiền phát hành, số bản dựng và thông tin tùy chọn trong mô hình phiên bản Java (Java 10+)

## 1. Phạm vi bài học và ý chính

Từ **Java 10**, Java sử dụng mô hình đánh số phiên bản theo chu kỳ phát hành được mô tả trong **JEP 322 — Time-Based Release Versioning**. Một phiên bản Java có **phần số phiên bản** và có thể kèm ba thành phần không bắt buộc:

- **Tiền phát hành — `PRE` (*pre-release identifier*)**: nhãn của bản chưa phát hành chính thức, ví dụ `ea`.
- **Số bản dựng — `BUILD` (*build number*)**: số thứ tự của một bản build được quảng bá, ví dụ `19` sau dấu `+`.
- **Thông tin tùy chọn — `OPT` (*optional build information*)**: mô tả bổ sung từ nhà phân phối/build, ví dụ `LTS`.

Ví dụ:

~~~text
10-ea+19
│  │  └── BUILD = 19
│  └───── PRE   = ea
└──────── VNUM  = 10

21.0.2+13-LTS
│      │  └──── OPT   = LTS
│      └─────── BUILD = 13
└────────────── VNUM  = 21.0.2

10+-LTS
│   └────────── OPT   = LTS
└────────────── VNUM  = 10
             Không có PRE, không có BUILD
~~~

**Không nhầm:** `-ea` gắn với **PRE**, `+19` gắn với **BUILD**, và `-LTS` ở phía sau build gắn với **OPT**. Cách phân tách phụ thuộc **vị trí và cấu trúc toàn bộ chuỗi**, không phải chỉ tìm một dấu `-` bất kỳ.

Trong mã Java hiện hành, dùng **`Runtime.Version`** để đọc và so sánh chính xác các thành phần. Lớp `Runtime.Version` có từ **Java 9**; Java 10 cập nhật ngữ nghĩa và bổ sung các accessor `feature()`, `interim()`, `update()`, `patch()`. Các API này vẫn có mặt trong Java mới. Không nên dùng các tên accessor đã deprecated `major()`, `minor()` hoặc `security()` trong mã mới.

## 2. Bối cảnh: phần số phiên bản và JEP 322

Một version string gồm hai lớp thông tin:

1. **`VNUM`** — phần số phiên bản, ví dụ `10`, `10.0.2`, `21.0.2.1`.
2. Các thành phần **`PRE`**, **`BUILD`**, **`OPT`**, tùy phiên bản có thể có hoặc không.

JEP 322 đặt tên bốn vị trí chính của phần số:

~~~text
$FEATURE.$INTERIM.$UPDATE.$PATCH
~~~

| Vị trí | Accessor hiện hành | Ý nghĩa |
| --- | --- | --- |
| `FEATURE` | `feature()` | Số chu kỳ phát hành tính năng |
| `INTERIM` | `interim()` | Số phát hành trung gian, nếu có |
| `UPDATE` | `update()` | Số cập nhật tương thích, thường là bảo mật/sửa lỗi |
| `PATCH` | `patch()` | Số bản vá khẩn cấp nếu phát hành theo dạng đó |

Các thành phần ở phía cuối bằng `0` được **bỏ khi viết chuỗi phiên bản**. Vì vậy `21` là cách viết thông thường khi ba vị trí tiếp theo bằng 0; `21.0.2` có phần INTERIM bằng 0 để đặt UPDATE ở vị trí thứ ba.

~~~java
Runtime.Version v = Runtime.Version.parse("21.0.2");

System.out.println(v.feature()); // 21
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 2
System.out.println(v.patch());   // 0
~~~

Đây là **đoạn minh họa trong một phương thức**. Các accessor trả `int`. Nếu vị trí INTERIM/UPDATE/PATCH không được viết, accessor tương ứng trả `0`.

**Không thể bỏ một số 0 ở giữa.** Chẳng hạn `21.0.2` không đồng nghĩa với `21.2`: ở chuỗi trước UPDATE là 2; ở chuỗi sau INTERIM là 2.

**Các số ở cuối đều bằng 0 không được ghi dư.** Theo cú pháp chính thức, `21.0.0` không hợp lệ để truyền cho `Runtime.Version.parse` vì phần số có số 0 thừa ở cuối. Ngoài ra, `021` không hợp lệ vì có số 0 dẫn đầu. `21.0.2` hợp lệ vì số 0 đó nằm ở giữa và cần cho vị trí UPDATE.

Phần số giúp phân biệt các chu kỳ phát hành và cập nhật. **`PRE`, `BUILD` và `OPT` nằm ngoài bốn vị trí số này**, nên `feature()` không tự trả “nhãn EA” hay số build.

## 3. Cú pháp chính thức của version string

Java SE hiện hành mô tả **ba hình thức** version string:

~~~text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+-$OPT)?
~~~

Ký hiệu `?` trong biểu thức mô tả thành phần **có thể vắng mặt**, không phải ký tự `?` xuất hiện trong một phiên bản thực tế. Dấu `+` và `-` là ký tự phân tách thực.

Đọc theo ví dụ:

| Chuỗi | VNUM | PRE | BUILD | OPT |
| --- | --- | --- | --- | --- |
| `10` | `10` | Không có | Không có | Không có |
| `10-ea` | `10` | `ea` | Không có | Không có |
| `10-ea+19` | `10` | `ea` | `19` | Không có |
| `10+19` | `10` | Không có | `19` | Không có |
| `10+19-LTS` | `10` | Không có | `19` | `LTS` |
| `10-ea-LTS` | `10` | `ea` | Không có | `LTS` |
| `10+-LTS` | `10` | Không có | Không có | `LTS` |
| `21.0.2+13-LTS` | `21.0.2` | Không có | `13` | `LTS` |

**Điểm dễ nhầm nhất:** chuỗi `10+-LTS` **không chứa build number** mặc dù có dấu `+`. Trong trường hợp này, `+-` là cách biểu diễn **OPT khi không có PRE và không có BUILD**. Javadoc đưa ra chính ví dụ `10+-ea`: nhãn `ea` ở đó là **OPT**, không phải PRE.

Ngược lại:

~~~text
10-ea          → PRE=ea, OPT không có
10+-ea         → PRE không có, OPT=ea
10-ea+19       → PRE=ea, BUILD=19
10+19-ea       → BUILD=19, OPT=ea
~~~

Hai chuỗi có cùng chữ `ea` vẫn có **ngữ nghĩa API khác nhau** do vị trí: `pre()` chỉ trả về giá trị khi đúng là thành phần tiền phát hành.

### Cú pháp của từng thành phần

Theo hợp đồng `Runtime.Version`:

- **`PRE`**: một hoặc nhiều ký tự **chữ cái ASCII hoặc chữ số**; biểu thức `[a-zA-Z0-9]+`. Ví dụ `ea`, `internal`, `rc1`, `2`. Dấu chấm và dấu gạch ngang **không nằm bên trong một PRE đơn lẻ**.
- **`BUILD`**: một số nguyên không âm dưới dạng thập phân, **`0` hoặc số không có số 0 dẫn đầu**. Ví dụ `0`, `13`, `142`. `+013` không phải dạng build chuẩn.
- **`OPT`**: chuỗi thông tin bổ sung có thể gồm chữ cái, chữ số, dấu chấm hoặc dấu gạch ngang theo giới hạn Javadoc. Ví dụ `LTS` hoặc thông tin định danh build của nhà phân phối.

Với dữ liệu nhận từ bên ngoài, hãy để `Runtime.Version.parse` áp dụng cú pháp và **bắt ngoại lệ** thay vì tự viết parser bằng `split("-")` hoặc `split("+")`. Regex tự phát có thể phân tách sai `10+-LTS` và `10-ea-LTS`.

## 4. `PRE` — nhãn tiền phát hành

**`PRE`** phân biệt một phiên bản chưa được xem là bản hoàn chỉnh so với bản không mang nhãn tiền phát hành, ở cùng phần số phiên bản.

Ví dụ:

~~~text
21-ea
21-ea+35
21-internal+4
21-rc1+12
21
~~~

`ea` thường dùng cho **early access**; `internal` thường dùng cho bản xây dựng nội bộ. Nhưng quy tắc `Runtime.Version` chỉ quy định **dạng ký tự và thứ tự so sánh**, không có một bảng chuẩn bắt buộc ánh xạ mọi nhãn thành trạng thái phát hành thực tế.

### Đọc `PRE` bằng API

~~~java
Runtime.Version candidate =
        Runtime.Version.parse("21-ea+35");

System.out.println(candidate.pre().orElse("<none>")); // ea
System.out.println(candidate.build().orElse(-1));      // 35

Runtime.Version stable = Runtime.Version.parse("21");
System.out.println(stable.pre().isEmpty()); // true
~~~

`pre()` trả **`Optional<String>`**:

- Có nhãn: trả `Optional` chứa chuỗi, chẳng hạn `ea`.
- Không có nhãn: trả `Optional.empty()`.
- Không nên gọi `pre().get()` nếu chưa kiểm tra có giá trị.

### So sánh bản tiền phát hành với bản không PRE

Theo `compareTo`, ở **cùng phần số phiên bản**, chuỗi **có PRE** được xem là **nhỏ hơn** chuỗi không có PRE:

~~~java
var early = Runtime.Version.parse("21-ea+35");
var release = Runtime.Version.parse("21");

System.out.println(early.compareTo(release) < 0); // true
~~~

Điều này **không có nghĩa** bạn phải cài đặt phiên bản có số lớn hơn dù đang EA. Ví dụ, `22-ea` vẫn có phần số lớn hơn `21` và có thể so sánh lớn hơn `21` theo thứ tự phiên bản. **Chính sách “chỉ dùng bản phát hành ổn định” là chính sách riêng**; khi cần, hãy kiểm tra `pre().isEmpty()` ngoài yêu cầu số phiên bản tối thiểu.

### Thứ tự giữa hai PRE

Khi phần số phiên bản bằng nhau và cả hai đều có PRE:

- Nếu hai chuỗi PRE đều chỉ chứa chữ số, so sánh **theo giá trị số**, ví dụ `2` nhỏ hơn `10`.
- PRE chỉ gồm chữ số được coi là **nhỏ hơn** PRE không phải toàn chữ số.
- Trường hợp còn lại so sánh **theo thứ tự chữ cái/chuỗi** (*lexicographical*), không dùng thứ tự release stage tùy ý như “alpha → beta → rc”.

~~~java
var p2 = Runtime.Version.parse("21-2");
var p10 = Runtime.Version.parse("21-10");
var pea = Runtime.Version.parse("21-ea");

System.out.println(p2.compareTo(p10) < 0); // true
System.out.println(p2.compareTo(pea) < 0); // true
~~~

**Đừng tự coi `rc`, `beta`, `ea` và `alpha` là các mốc phát hành có thứ tự nghiệp vụ cố định.** `Runtime.Version.compareTo` thực hiện đúng thứ tự theo Javadoc, nhưng không xác minh được những nhãn ấy có được nhà cung cấp sử dụng theo một quy trình thực tế hay không.

## 5. `BUILD` — số bản dựng sau dấu `+`

**`BUILD`** là **số bản dựng được quảng bá** (*promoted build number*) của phiên bản. Nó nằm sau dấu `+` khi có giá trị số:

~~~text
21+1           → BUILD=1
21+35          → BUILD=35
21-ea+35       → PRE=ea, BUILD=35
21.0.2+13-LTS  → BUILD=13, OPT=LTS
21+0           → BUILD=0, vẫn có BUILD
~~~

Số build không phải:

- Số phiên bản tính năng `feature()`.
- Số bản vá `update()` hoặc `patch()`.
- Ngày phát hành hay mã định danh commit của nhà sản xuất.
- Dấu hiệu tự động về an toàn bảo mật hoặc trạng thái đã phát hành.

JEP 322/Javadoc mô tả build được **tăng theo các bản được quảng bá** và **đặt lại khi phần số VNUM tăng**. Tuy nhiên cách phân phối runtime của từng nhà cung cấp có thể có quy trình riêng; **không thể suy từ một build number rằng chương trình đã nhận đầy đủ mọi bản sửa bảo mật**.

### Đọc BUILD an toàn

~~~java
var built = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(built.build().orElse(-1)); // 13
System.out.println(built.optional().orElse("<none>")); // LTS

var noBuild = Runtime.Version.parse("21-ea");

System.out.println(noBuild.build().isEmpty()); // true
~~~

`build()` trả **`Optional<Integer>`**. **Không có BUILD** và **BUILD có giá trị `0`** là hai trạng thái khác nhau:

~~~java
var absent = Runtime.Version.parse("21");
var zero = Runtime.Version.parse("21+0");

System.out.println(absent.build().isEmpty()); // true
System.out.println(zero.build().orElse(-1));  // 0
~~~

Không dùng `build().orElse(0)` rồi mặc định “0 nghĩa là chưa có build” nếu ứng dụng cần phân biệt hai trường hợp.

### BUILD trong thứ tự so sánh

Khi VNUM và PRE giống nhau:

- Một version **không có BUILD** được so sánh **nhỏ hơn** version có BUILD.
- Hai BUILD có mặt được so sánh **bằng số nguyên**.

~~~java
System.out.println(
        Runtime.Version.parse("21")
                .compareTo(Runtime.Version.parse("21+1")) < 0);
// true

System.out.println(
        Runtime.Version.parse("21+12")
                .compareTo(Runtime.Version.parse("21+13")) < 0);
// true
~~~

**Lưu ý khác Semantic Versioning (SemVer 2.0):** SemVer coi dấu `+...` là metadata **không ảnh hưởng precedence**, còn mô hình `Runtime.Version` của Java **có xét BUILD** khi so sánh. Đừng dùng quy tắc SemVer của npm/Maven/ứng dụng khác để giải thích kết quả `Runtime.Version.compareTo`.

## 6. `OPT` — thông tin bổ sung tùy chọn

**`OPT`** là **optional identifying build information**. Nó có thể được nhà sản xuất runtime dùng để gắn thông tin nhận diện build, ví dụ ký hiệu `LTS` hoặc thông tin về một bản dựng nội bộ.

Các ví dụ minh họa:

~~~text
21.0.2+13-LTS      → OPT=LTS
21.0.2+13-vendor   → OPT=vendor
21-ea-internal     → PRE=ea, OPT=internal, BUILD vắng mặt
21+-LTS            → OPT=LTS, PRE và BUILD đều vắng mặt
~~~

**`OPT` không phải PRE.** Trong `21+13-LTS`, `LTS` là thông tin tùy chọn bổ sung, không có nghĩa bản này là tiền phát hành.

### Cách đọc OPT

~~~java
var version = Runtime.Version.parse("21.0.2+13-LTS");

System.out.println(version.pre().isEmpty());      // true
System.out.println(version.build().orElse(-1));    // 13
System.out.println(version.optional().orElse("?")); // LTS
~~~

`optional()` trả **`Optional<String>`**. Khi không có OPT, nó trả `Optional.empty()`. Chuỗi OPT không nhất thiết là một mã trạng thái được Java chuẩn hóa đầy đủ: API giữ **thông tin nhận dạng**, còn chính sách cụ thể phụ thuộc nhà sản xuất.

### Ý nghĩa của nhãn `LTS`

Trong JEP 322, nhà triển khai có thể bắt đầu OPT bằng `LTS` để đánh dấu bản thuộc một dòng phát hành mà nhà triển khai **cung cấp hỗ trợ dài hạn**. Ví dụ `11.0.2+13-LTS` là ví dụ cú pháp được JEP sử dụng.

Nhưng:

- `Runtime.Version.parse("21+13-LTS")` **chỉ phân tích một chuỗi**; nó không kiểm chứng thực tế có hợp đồng support nào.
- Nhãn `LTS` **không tự bảo đảm** bản build đã vá lỗi mới nhất, có chính sách cập nhật tự động, có hạn hỗ trợ bao lâu hoặc được phép dùng theo một giấy phép cụ thể.
- Để biết vòng đời hỗ trợ, mức vá bảo mật, giấy phép và lịch cập nhật, phải kiểm tra **nhà cung cấp bản JDK** và tài liệu phát hành tương ứng.
- Không được suy luận rằng mọi runtime cùng feature number có chính sách hỗ trợ giống nhau.

### OPT có thể tồn tại khi không có build

~~~java
var v = Runtime.Version.parse("21+-LTS");

System.out.println(v.pre().isEmpty()); // true
System.out.println(v.build().isEmpty()); // true
System.out.println(v.optional().orElse("<none>")); // LTS
~~~

Đây là một cú pháp được Javadoc thừa nhận, **không phải lỗi** và **không có số build ẩn**. Dấu `+` trong dạng `+-OPT` chỉ là một phần của cú pháp phân tách OPT.

## 7. Khi nào PRE, BUILD, OPT vắng mặt?

Các getter trả về `Optional`, không phải giá trị mặc định có ý nghĩa mơ hồ:

| Phiên bản | `pre()` | `build()` | `optional()` |
| --- | --- | --- | --- |
| `10` | Empty | Empty | Empty |
| `10-ea` | `ea` | Empty | Empty |
| `10-ea+19` | `ea` | `19` | Empty |
| `10+19-LTS` | Empty | `19` | `LTS` |
| `10-ea-LTS` | `ea` | Empty | `LTS` |
| `10+-LTS` | Empty | Empty | `LTS` |
| `10+0` | Empty | `0` | Empty |

`Optional.empty()` có nghĩa là **thành phần không xuất hiện** trong chuỗi. Nó không có nghĩa rằng Java đã phân tích được một giá trị mặc định cụ thể:

- PRE vắng mặt: không có nhãn pre-release trên version string.
- BUILD vắng mặt: chuỗi không cung cấp số build.
- OPT vắng mặt: chuỗi không chứa thông tin nhận diện bổ sung.

**Đừng đưa `null` vào trình bày nếu có thể dùng Optional đúng cách.** Ví dụ:

~~~java
var v = Runtime.Version.parse("21-ea+35");

String stage = v.pre().orElse("release");
String buildText = v.build()
        .map(Object::toString)
        .orElse("not specified");
String opt = v.optional().orElse("none");
~~~

Đây là **đoạn mã minh họa trong một phương thức**. Đặc biệt, `pre().isEmpty()` không nên bị hiểu là bằng chứng được nhà phân phối xác thực bản đã phát hành thương mại; nó chỉ nói chuỗi không chứa PRE.

## 8. Cách `Runtime.Version` so sánh các thành phần

Javadoc `Runtime.Version.compareTo` quy định so sánh theo thứ tự ưu tiên **từ trái sang phải**:

1. **Phần số VNUM**, theo từng thành phần số.
2. **PRE**, nếu phần số bằng nhau.
3. **BUILD**, nếu PRE cũng bằng nhau.
4. **OPT**, nếu ba nhóm trước bằng nhau.

### Bước 1: phần số trước

~~~text
21.0.1+99    <   21.0.2
21.0.2       <   22-ea
~~~

Ví dụ chỉ minh họa **thứ tự theo số phiên bản**. Build 99 của `21.0.1` không thể làm nó lớn hơn `21.0.2` theo thuật toán Java, vì VNUM được so sánh đầu tiên.

### Bước 2: PRE

Ở cùng VNUM, có PRE < không có PRE. Trong hai PRE, so sánh theo quy tắc numeric/lexicographic nêu ở phần 4.

~~~text
21-ea+99     <   21
21-2         <   21-10
21-2         <   21-ea
~~~

### Bước 3: BUILD

Ở cùng VNUM và PRE, không có BUILD < có BUILD; hai BUILD có số thì so bằng số:

~~~text
21           <   21+1
21+12        <   21+13
21-ea+2      <   21-ea+10
~~~

### Bước 4: OPT

Đây là điểm khiến hai phiên bản có **cùng VNUM, PRE, BUILD** vẫn khác nhau theo `compareTo`:

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equals(b)); // false
System.out.println(a.compareTo(b) != 0); // true
~~~

OPT được so sánh **theo thứ tự chuỗi**, và khi chỉ một bên có OPT thì bên **có OPT** được coi là lớn hơn bên không có.

**Không sử dụng thứ tự này như thứ tự chất lượng/độ bảo mật của các nhà sản xuất JDK.** Java định nghĩa cách so sánh chuỗi phiên bản, không đưa ra bảng xếp hạng vendor hay mức độ ổn định vận hành.

### Dùng đúng cặp phương thức so sánh và bằng nhau

- `compareTo(other)` tương ứng với `equals(other)`: có xét OPT.
- `compareToIgnoreOptional(other)` tương ứng với `equalsIgnoreOptional(other)`: **bỏ qua OPT**.

Nếu bạn dùng một phương thức so sánh trong `TreeSet`/`TreeMap` để xác định trùng và thứ tự, hãy hiểu rõ định nghĩa equality của ứng dụng. `equalsIgnoreOptional` không thay đổi `equals`/`hashCode` mặc định của đối tượng.

## 9. `compareToIgnoreOptional` và `equalsIgnoreOptional`

Hai phương thức này đặc biệt hữu ích nếu ứng dụng muốn so sánh phiên bản Java **không tính chuỗi nhận diện build tùy chọn**.

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");

System.out.println(a.equalsIgnoreOptional(b)); // true
System.out.println(a.equals(b));               // false

System.out.println(a.compareToIgnoreOptional(b)); // 0
System.out.println(a.compareTo(b) != 0);           // true
~~~

**Chỉ OPT được bỏ qua**, không phải toàn bộ thông tin sau dấu `+`. Ví dụ:

~~~java
var build12 = Runtime.Version.parse("21+12-LTS");
var build13 = Runtime.Version.parse("21+13-vendor");

System.out.println(
        build12.compareToIgnoreOptional(build13) < 0);
// true: BUILD=12 nhỏ hơn BUILD=13.
~~~

Khi **không quan tâm nhà phân phối nhưng vẫn cần so build**, dùng cặp IgnoreOptional là đúng theo tên. Nếu nghiệp vụ **không quan tâm cả BUILD**, cần tự xác định tập thành phần được so; `compareToIgnoreOptional` **vẫn so BUILD**.

### Tránh dùng `==`

`Runtime.Version` là một **value-based class**. Không sử dụng identity/reference equality `==` hoặc bản thân đối tượng để khóa đồng bộ. Kiểm tra giá trị bằng `equals` hoặc `equalsIgnoreOptional` đúng mục đích.

## 10. Chương trình Java đầy đủ: tách thành phần, so sánh, xử lý lỗi

Chương trình dưới đây không phụ thuộc version đang cài trên máy, vì nó **phân tích các chuỗi ví dụ cố định**. Lưu thành **`VersionPartsDemo.java`**:

~~~java
public class VersionPartsDemo {

    private static void show(String text) {
        Runtime.Version v = Runtime.Version.parse(text);

        System.out.println(text
                + " => num=" + v.version()
                + ",pre=" + v.pre().orElse("<none>")
                + ",build=" + v.build()
                        .map(Object::toString).orElse("<none>")
                + ",optional=" + v.optional().orElse("<none>"));
    }

    private static void bad(String label, String text) {
        try {
            Runtime.Version.parse(text);
            System.out.println(label + "=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + "=rejected");
        }
    }

    public static void main(String[] args) {
        show("10-ea");
        show("10-ea+19");
        show("10+19-LTS");
        show("10-ea-LTS");
        show("10+-LTS");
        show("10.0.2+13-LTS");
        show("10+0");

        Runtime.Version v =
                Runtime.Version.parse("21.0.2.1-ea+13-vendor");

        System.out.println("feature=" + v.feature());
        System.out.println("interim=" + v.interim());
        System.out.println("update=" + v.update());
        System.out.println("patch=" + v.patch());
        System.out.println("pre=" + v.pre().orElse("none"));
        System.out.println("build=" + v.build().orElse(-1));
        System.out.println("optional=" + v.optional().orElse("none"));

        System.out.println("eaBeforeGA="
                + (Runtime.Version.parse("21-ea+30")
                .compareTo(Runtime.Version.parse("21+1")) < 0));

        System.out.println("releaseBeforeBuilt="
                + (Runtime.Version.parse("21")
                .compareTo(Runtime.Version.parse("21+1")) < 0));

        System.out.println("build12Before13="
                + (Runtime.Version.parse("21+12")
                .compareTo(Runtime.Version.parse("21+13")) < 0));

        Runtime.Version a =
                Runtime.Version.parse("21.0.2+13-LTS");
        Runtime.Version b =
                Runtime.Version.parse("21.0.2+13-vendor");

        System.out.println("sameIgnoreOptional="
                + a.equalsIgnoreOptional(b));
        System.out.println("sameStrict=" + a.equals(b));
        System.out.println("compareIgnoreOptional="
                + a.compareToIgnoreOptional(b));
        System.out.println("compareStrictNonzero="
                + (a.compareTo(b) != 0));

        System.out.println("numericPreLess="
                + (Runtime.Version.parse("21-2")
                .compareTo(Runtime.Version.parse("21-10")) < 0));
        System.out.println("numericBeforeAlpha="
                + (Runtime.Version.parse("21-2")
                .compareTo(Runtime.Version.parse("21-ea")) < 0));

        System.out.println("runtimeFeaturePositive="
                + (Runtime.version().feature() > 0));

        bad("trailingZero", "21.0.0");
        bad("leadingZero", "021");
        bad("emptyBuild", "21+");

        try {
            Runtime.Version.parse(null);
        } catch (NullPointerException ex) {
            System.out.println("nullVersion=NPE");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**. Các API hiện hành trong ví dụ tương thích **Java 10+**:

~~~bash
javac VersionPartsDemo.java
java VersionPartsDemo
~~~

**`stdout` đã được kiểm tra bằng JDK 24:**

~~~text
10-ea => num=[10],pre=ea,build=<none>,optional=<none>
10-ea+19 => num=[10],pre=ea,build=19,optional=<none>
10+19-LTS => num=[10],pre=<none>,build=19,optional=LTS
10-ea-LTS => num=[10],pre=ea,build=<none>,optional=LTS
10+-LTS => num=[10],pre=<none>,build=<none>,optional=LTS
10.0.2+13-LTS => num=[10, 0, 2],pre=<none>,build=13,optional=LTS
10+0 => num=[10],pre=<none>,build=0,optional=<none>
feature=21
interim=0
update=2
patch=1
pre=ea
build=13
optional=vendor
eaBeforeGA=true
releaseBeforeBuilt=true
build12Before13=true
sameIgnoreOptional=true
sameStrict=false
compareIgnoreOptional=0
compareStrictNonzero=true
numericPreLess=true
numericBeforeAlpha=true
runtimeFeaturePositive=true
trailingZero=rejected
leadingZero=rejected
emptyBuild=rejected
nullVersion=NPE
~~~

**Giải thích kết quả quan trọng:**

1. Bảy dòng đầu phân tách **tất cả các trường hợp ngữ pháp**: chỉ PRE, PRE+BUILD, BUILD+OPT, PRE+OPT, chỉ OPT, phiên bản cập nhật có BUILD+OPT, và BUILD=0.
2. Với `21.0.2.1-ea+13-vendor`, bốn thành phần số là `21/0/2/1`, PRE là `ea`, BUILD là `13`, OPT là `vendor`.
3. `eaBeforeGA=true`: cùng feature 21, bản có PRE nhỏ hơn bản không PRE.
4. `releaseBeforeBuilt=true`: khi mọi phần trước giống nhau, thiếu BUILD nhỏ hơn có BUILD, theo quy tắc của `Runtime.Version`.
5. `sameIgnoreOptional=true` và `compareIgnoreOptional=0`: hai chuỗi chỉ khác OPT được coi tương đương nếu bỏ OPT.
6. `sameStrict=false` và `compareStrictNonzero=true`: quy tắc mặc định vẫn phân biệt OPT.
7. `numericPreLess=true` và `numericBeforeAlpha=true`: PRE toàn số có quy tắc so sánh riêng.
8. `runtimeFeaturePositive=true`: kiểm tra với runtime thật mà **không hardcode** số Java của máy chạy.
9. `trailingZero=rejected`, `leadingZero=rejected`, `emptyBuild=rejected`: các chuỗi minh họa sai cú pháp bị từ chối.
10. `nullVersion=NPE`: truyền `null` cho `parse` bị từ chối bằng `NullPointerException`.

**Bài test dùng giá trị chuỗi cố định** để không phụ thuộc phiên bản runtime cụ thể. Dòng duy nhất đọc runtime thật kiểm tra một thuộc tính rất cơ bản, không in số feature để tránh biến đầu ra thành phụ thuộc máy.

## 11. Runtime hiện đang chạy và chuỗi được báo bởi công cụ

Để đọc version của **JVM đang chạy**, không cần tự phân tích kết quả màn hình:

~~~java
Runtime.Version running = Runtime.version();

int feature = running.feature();
int update = running.update();

String prerelease = running.pre().orElse("<none>");
String build = running.build()
        .map(Object::toString)
        .orElse("<not supplied>");
String extra = running.optional().orElse("<none>");
~~~

Đây là **đoạn minh họa trong phương thức**. `Runtime.version()` lấy `Runtime.Version` của môi trường thực, khác `Runtime.Version.parse("21+13")` — phương thức parse chỉ **đọc một chuỗi ví dụ**, không tìm hay cài đặt JVM tương ứng.

### Các cách kiểm tra khi vận hành

Trong terminal:

~~~bash
java --version
java --full-version
~~~

Trong Java:

~~~java
System.out.println(Runtime.version());
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.runtime.version"));
System.out.println(System.getProperty("java.vendor"));
~~~

Đầu ra phụ thuộc **bản phân phối JDK/JRE cụ thể**, không nên đưa một stdout cứng vào bài rồi coi là đúng ở mọi môi trường.

- `java --version` hiển thị dòng nhận dạng và các thông tin runtime tùy nhà triển khai.
- `java --full-version` cung cấp thông tin phiên bản đầy đủ theo launcher.
- `java.version` là thuộc tính phiên bản của Java runtime.
- `java.runtime.version` thường cung cấp phiên bản build runtime đầy đủ hơn.
- `java.vendor` là tên nhà cung cấp; nó **không phải OPT**.

**Đừng parse nguyên dòng `java --version` bằng `Runtime.Version.parse`.** Dòng đó có thể kèm tên runtime, ngày phát hành, ký hiệu LTS, thông tin VM và vendor. `parse` nhận **một version string chuẩn**, không phải toàn bộ thông báo của chương trình launcher.

Khi cần biết chạy Java feature bao nhiêu trong mã, **`Runtime.version().feature()` là trực tiếp và rõ nghĩa**, tránh dựa vào thủ công tách chuỗi theo dấu chấm rồi ép `int`.

## 12. `java.version`, `java.runtime.version` và thông tin vendor

Cùng một bản JDK có thể hiển thị:

- **Số phiên bản nền tảng** phục vụ nhận diện Java feature/update.
- **Chuỗi phiên bản runtime** có thông tin build.
- **Thông tin tùy chọn** bên trong phiên bản build.
- **Phiên bản sản phẩm riêng của nhà cung cấp**, nếu có.

JEP 322 bổ sung thuộc tính `java.vendor.version` để nhà triển khai có thể công bố **phiên bản sản phẩm riêng**; nó không đồng nghĩa với `Runtime.Version.optional()`.

~~~java
String vendor = System.getProperty("java.vendor");
String vendorVersion = System.getProperty("java.vendor.version");

String runtimeVersion =
        System.getProperty("java.runtime.version");
~~~

`vendorVersion` có thể không được gán; đừng mặc định luôn có giá trị. Khi hiển thị log hay lập dữ liệu hỗ trợ sự cố, lưu cả **vendor, phiên bản runtime, feature/update** có thể có ích hơn chỉ lưu một nhãn tùy chọn.

**Phân biệt ba trường:**

| Trường | Câu hỏi nó trả lời |
| --- | --- |
| `Runtime.version().build()` | Bản build số bao nhiêu, nếu version string có BUILD? |
| `Runtime.version().optional()` | Có chuỗi thông tin bổ sung nào gắn trong version string? |
| `System.getProperty("java.vendor.version")` | Nhà cung cấp có khai báo phiên bản sản phẩm riêng ngoài chuỗi Runtime.Version không? |

Không đồng nhất tên của runtime với mã Java feature. Hai nhà cung cấp có thể cùng feature/update mà khác số build, cách gắn OPT, chính sách hỗ trợ và lịch bảo trì.

### `LTS` và chính sách hỗ trợ

Nếu thấy `optional().orElse("")` bắt đầu bằng `LTS`, có thể hiểu **nhà triển khai đã đưa nhãn đó vào metadata**. Nhưng điều này không phải chứng chỉ độc lập bảo đảm hiệu lực support. Dùng thông tin nhà cung cấp và bản phát hành cụ thể nếu phải ra quyết định cập nhật, bảo mật hoặc tuân thủ.

Không nên kết luận “không có OPT=LTS nghĩa là bản Java không được bất kỳ bên nào hỗ trợ lâu dài”, vì metadata và chính sách phân phối có thể khác nhau.

## 13. Kiểm tra yêu cầu phiên bản Java một cách thực dụng

### Kiểm tra một API cần Java feature tối thiểu

Nếu một tính năng chỉ có từ Java 17, có thể dùng:

~~~java
boolean hasRequiredFeature =
        Runtime.version().feature() >= 17;
~~~

Nhưng kiểm tra phiên bản **không tự thay thế** việc biên dịch trên đúng `--release` hoặc kiểm tra dependency runtime. Một thư viện có thể yêu cầu một API cụ thể đã xuất hiện ở bản cập nhật khác hoặc bị giới hạn do module, vendor hay môi trường chạy.

Với build pipeline, hãy xác định mục tiêu rõ:

~~~bash
javac --release 17 MyProgram.java
~~~

`--release` giới hạn ngôn ngữ và API mục tiêu theo bản release mà compiler hỗ trợ; nó giúp tránh vô tình biên dịch một chương trình cho Java 17 bằng API chỉ có ở bản mới hơn. Đoạn lệnh giả định có tệp `MyProgram.java`. Đó là kiểm soát tương thích lúc build, không phải cơ chế lựa chọn JDK runtime đang chạy.

### Kiểm tra có phải pre-release

~~~java
Runtime.Version running = Runtime.version();

boolean hasPreReleaseLabel = running.pre().isPresent();
~~~

Khi chính sách ứng dụng không cho chạy trên bản tiền phát hành, có thể dùng `pre().isEmpty()` như một phần kiểm tra. **Không kết luận rằng nhãn PRE vắng mặt là đủ chứng minh bản runtime đã được vendor chứng nhận bảo mật**, vì các điều kiện hỗ trợ vận hành khác tồn tại.

### So sánh một ngưỡng cụ thể

~~~java
var minimum = Runtime.Version.parse("21.0.2");
var current = Runtime.version();

boolean notOlderThanMinimum =
        current.compareToIgnoreOptional(minimum) >= 0;
~~~

Lời gọi này so sánh phần số, PRE và BUILD theo quy tắc Java **và bỏ OPT**. Nhưng hãy cẩn thận:

- Nếu ngưỡng có build number, bản cùng VNUM **không có build** có thể bị coi là nhỏ hơn.
- Một bản `22-ea` có VNUM lớn hơn ngưỡng `21`; nếu không chấp nhận EA, cần kiểm tra **`current.pre().isEmpty()`** riêng.
- `compareToIgnoreOptional` vẫn xét build; nếu mục tiêu chỉ là feature/update, hãy so đúng các trường số cần thiết.
- Mức vá bảo mật **không thể được xác nhận hoàn toàn** chỉ bằng cách so chuỗi phiên bản, nhất là khi có nhà cung cấp backport các bản vá.

**Quy tắc tốt:** tách rõ hai câu hỏi “runtime có phiên bản API mong muốn?” và “bản phân phối đang chạy có được bảo trì và vá lỗi phù hợp?” — chúng không có cùng câu trả lời.

## 14. Những chuỗi không hợp lệ và ngoại lệ của `parse`

`Runtime.Version.parse(String)` dùng cú pháp chặt chẽ. Nó **không** chấp nhận mọi chuỗi nhìn giống số phiên bản.

Ví dụ:

| Input | Kết quả |
| --- | --- |
| `"21"` | Hợp lệ |
| `"21.0.2"` | Hợp lệ |
| `"21-ea+35"` | Hợp lệ |
| `"21+0"` | Hợp lệ; BUILD=0 |
| `"21+-LTS"` | Hợp lệ; chỉ OPT |
| `"21.0.0"` | Không hợp lệ: trailing zero elements |
| `"021"` | Không hợp lệ: leading zero |
| `"21+"` | Không hợp lệ: thiếu build/OPT |
| `"21.0.2+013"` | Không hợp lệ: số build có leading zero |
| `null` | `NullPointerException` |

Ngoại lệ theo Javadoc:

- **`IllegalArgumentException`**: không thể diễn giải chuỗi thành version string hợp lệ.
- **`NullPointerException`**: đối số `s` là null.
- **`NumberFormatException`**: phần số phiên bản hoặc BUILD vượt phạm vi một `Integer`. Lưu ý `NumberFormatException` là một **lớp con của `IllegalArgumentException`**.

Ví dụ xử lý đầu vào:

~~~java
String userInput = "21.0.2+13-LTS";

try {
    Runtime.Version parsed = Runtime.Version.parse(userInput);
    System.out.println(parsed.feature());
} catch (NumberFormatException ex) {
    System.err.println("Version component exceeds int range");
} catch (IllegalArgumentException ex) {
    System.err.println("Invalid Java version string");
}
~~~

Đây là **đoạn minh họa trong một phương thức**. Nếu muốn phân loại `null` riêng, kiểm tra hoặc bắt `NullPointerException`. Không dựa vào **text của exception message** như một API ổn định.

### Parse hợp lệ không đồng nghĩa phiên bản thực sự tồn tại

~~~java
Runtime.Version fictional =
        Runtime.Version.parse("987-ea+12");
~~~

Một chuỗi có cú pháp hợp lệ được parse thành đối tượng. Điều đó **không xác minh có JDK phiên bản 987 đang được phát hành**, đã được vendor ký hay có gói tải tin cậy. `parse` là parser và công cụ so sánh, **không phải trình truy vấn kho phát hành Java**.

Cũng không nên dùng parser này cho phiên bản Maven/Gradle, container image hoặc Semantic Versioning không theo mô hình Java, dù chuỗi trông giống nhau.

## 15. Các lỗi phổ biến

| Hiểu sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`-ea` luôn là OPT.” | Trong `21-ea`, đó là PRE. | Xem vị trí toàn chuỗi; khác `21+-ea`. |
| “Mọi dấu `+` luôn theo sau bởi BUILD.” | `21+-LTS` có OPT nhưng không BUILD. | Xét dạng cú pháp `+-$OPT`. |
| “`+13-LTS` chứa BUILD bằng `13-LTS`.” | BUILD chỉ là số nguyên `13`. | `LTS` nằm ở OPT. |
| “BUILD giống UPDATE hoặc PATCH.” | BUILD nằm ngoài VNUM, không phải vị trí số thứ 3/4. | Dùng `build()`, `update()`, `patch()` riêng. |
| “`+0` nghĩa là không có BUILD.” | BUILD=0 vẫn hiện diện. | Phân biệt `Optional.of(0)` và `Optional.empty()`. |
| “Dấu `+` là metadata không dùng để sort như SemVer.” | Java `Runtime.Version` **so BUILD**. | Dùng quy tắc của Java, không suy từ SemVer. |
| “`compareToIgnoreOptional` bỏ qua mọi phần sau `+`.” | Chỉ bỏ OPT, **không bỏ BUILD**. | Chọn comparator phù hợp mục tiêu. |
| “Hai phiên bản cùng feature thì hoàn toàn giống nhau.” | UPDATE/PATCH/BUILD/PRE/OPT còn khác. | Chọn trường cần so theo chính sách cụ thể. |
| “`LTS` chắc chắn là bản mới nhất và được vá bảo mật.” | OPT là thông tin tùy chọn do producer gắn. | Xác minh vòng đời hỗ trợ với vendor. |
| “`Runtime.Version.parse` truy vấn được bản đang cài.” | Nó chỉ diễn giải input String. | Dùng `Runtime.version()` cho JVM hiện tại. |
| “`Runtime.version()` là số phiên bản của compiler.” | Nó là phiên bản runtime đang chạy. | Kiểm tra công cụ build và mục tiêu `--release` riêng. |
| “Chia chuỗi bằng dấu `-` là đủ.” | Có PRE, OPT và dạng `+-OPT`. | Dùng `Runtime.Version.parse`. |
| “`major()`/`minor()`/`security()` là cách mới.” | Các accessor này deprecated từ Java 10. | Dùng `feature()`, `interim()`, `update()`, `patch()`. |
| “Mọi `21.0.0` đều là chuỗi Java chuẩn.” | VNUM không có trailing zero. | Dùng `21` hoặc dạng hợp lệ tương ứng. |
| “Có thể dùng `Version` làm monitor bằng `synchronized`.” | `Runtime.Version` là value-based. | Dùng một object khóa riêng khi thực sự cần đồng bộ. |

## 16. Bài tập tự kiểm tra

### Bài 1: tách thành phần

Cho:

~~~text
21.0.2-ea+13-LTS
~~~

Hãy chỉ ra VNUM, PRE, BUILD và OPT.

**Đáp án:** VNUM=`21.0.2`, PRE=`ea`, BUILD=`13`, OPT=`LTS`. `feature()=21`, `interim()=0`, `update()=2`, `patch()=0`.

### Bài 2: hai chuỗi cùng ký hiệu `ea`

So sánh `21-ea` và `21+-ea`: `pre()` và `optional()` khác nhau ra sao?

**Đáp án:** Với `21-ea`, `pre()=ea` và `optional()` rỗng. Với `21+-ea`, `pre()` rỗng và `optional()=ea`. Ký hiệu giống nhau nhưng **vị trí xác định ngữ nghĩa**.

### Bài 3: phân biệt build bị thiếu và build bằng 0

`21` và `21+0` có cùng `build()` không?

**Đáp án:** Không. `Runtime.Version.parse("21").build()` là `Optional.empty()`; `Runtime.Version.parse("21+0").build()` chứa `0`.

### Bài 4: so sánh PRE với bản không PRE

Theo `compareTo`, `21-ea+35` hay `21` được coi lớn hơn?

**Đáp án:** `21` lớn hơn vì cùng VNUM mà bản có PRE được coi nhỏ hơn bản không có PRE.

### Bài 5: so BUILD

Giữa `21+9` và `21+10`, phiên bản nào lớn hơn theo Java?

**Đáp án:** `21+10` lớn hơn. BUILD được so bằng số, không theo thứ tự từ điển của chuỗi `9` và `10`.

### Bài 6: bỏ OPT

~~~java
var a = Runtime.Version.parse("21.0.2+13-LTS");
var b = Runtime.Version.parse("21.0.2+13-vendor");
~~~

`a.equals(b)` và `a.equalsIgnoreOptional(b)` trả gì?

**Đáp án:** `false` và `true`. Chúng khác OPT nhưng cùng các thành phần còn lại.

### Bài 7: `compareToIgnoreOptional` có bỏ BUILD không?

~~~java
var a = Runtime.Version.parse("21+12-LTS");
var b = Runtime.Version.parse("21+13-vendor");
~~~

**Đáp án:** Không. `a.compareToIgnoreOptional(b) < 0` vẫn là `true` vì BUILD 12 nhỏ hơn 13.

### Bài 8: chọn API lấy phiên bản JVM thực

Giữa `Runtime.Version.parse("21")` và `Runtime.version()`, cách nào lấy phiên bản **môi trường đang chạy**?

**Đáp án:** `Runtime.version()`. `parse("21")` chỉ tạo giá trị đại diện cho chuỗi `21`.

### Bài 9: đánh giá một nhãn `LTS`

Nếu `Runtime.version().optional()` trả chuỗi bắt đầu bằng `LTS`, có thể tự tin rằng toàn bộ cập nhật bảo mật đã có chưa?

**Đáp án:** Không. Nhãn chỉ cho thấy thông tin build được gắn; cần chính sách hỗ trợ, lịch cập nhật và advisory thực tế của nhà triển khai.

### Bài 10: phát hiện chuỗi sai

Trong các chuỗi `21+0`, `21.0.2`, `021`, `21.0.0`, `21+-LTS`, chuỗi nào `Runtime.Version.parse` chấp nhận?

**Đáp án:** `21+0`, `21.0.2` và `21+-LTS`. `021` có số 0 đầu; `21.0.0` có số 0 cuối ở phần số.

## 17. Tổng kết

- Mô hình phiên bản từ **Java 10 (JEP 322)** tách **VNUM** và các thành phần không bắt buộc **PRE**, **BUILD**, **OPT**.
- `PRE` mô tả **tiền phát hành**, ví dụ `ea`; `BUILD` là **số bản dựng nguyên không âm**; `OPT` là **thông tin nhận diện build tùy chọn** như `LTS`.
- Cùng chữ `ea` nhưng `21-ea` (PRE) và `21+-ea` (OPT) có ý nghĩa **khác nhau**.
- Dùng **`Runtime.Version.parse`** để đọc chuỗi theo cú pháp chuẩn, và `pre()`, `build()`, `optional()` để lấy các giá trị `Optional`.
- `Runtime.Version.compareTo` so **VNUM → PRE → BUILD → OPT**; `compareToIgnoreOptional` chỉ bỏ qua **OPT**, không bỏ qua BUILD.
- `feature()`, `interim()`, `update()`, `patch()` là các accessor hiện hành; tránh các tên đã deprecated ở Java 10.
- `Runtime.version()` cho phiên bản của **JVM đang chạy**; `parse(...)` chỉ diễn giải một chuỗi.
- `LTS` trong OPT và số BUILD **không thay thế** việc xác minh support, cập nhật bảo mật hoặc chính sách của nhà phân phối.
- **Không coi cú pháp Java giống SemVer hoàn toàn**: Java có những quy tắc riêng về BUILD và thứ tự so sánh.

### Tài liệu chính thức, hiện còn hiệu lực

1. [Java SE 26 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.Version.html): cú pháp VNUM/PRE/BUILD/OPT, `parse`, `pre`, `build`, `optional`, các quy tắc `compareTo`/`compareToIgnoreOptional`.
2. [Java SE 26 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html#version()): đọc phiên bản của runtime đang thực thi.
3. [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322): bối cảnh từ Java 10, bốn vị trí FEATURE/INTERIM/UPDATE/PATCH và hỗ trợ OPT như nhãn LTS.
4. [JEP 322 — bản tham khảo đầy đủ](https://cr.openjdk.org/~mr/jdk/jeps/322-time-based-release-versioning.html): các ví dụ, cách hiển thị launcher và dữ liệu vendor.
