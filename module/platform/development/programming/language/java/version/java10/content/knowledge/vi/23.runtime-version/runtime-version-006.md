# Java 10 — `Runtime.Version.compareTo()` và quy tắc so sánh phiên bản

## 1. Mục tiêu bài học

Ứng dụng Java đôi khi phải kiểm tra JDK hiện tại có đáp ứng một ngưỡng phiên bản, sắp xếp danh sách runtime để triển khai, chọn bản cập nhật mới hơn hoặc so sánh các build cùng một release. Chỉ so sánh **chuỗi** như `"17.0.10".compareTo("17.0.2")` là sai vì so sánh ký tự không hiểu các thành phần phiên bản là số.

Java cung cấp `java.lang.Runtime.Version` để biểu diễn và so sánh **chuỗi phiên bản của Java SE/JDK**. Phương thức chính là:

```java
int result = left.compareTo(right);
```

Đây là mảnh code trong phương thức, hai biến có kiểu `Runtime.Version`. Kết quả:
- `result < 0`: `left` đứng **trước** `right` theo quy tắc phiên bản;
- `result == 0`: hai phiên bản tương đương theo phép so sánh đầy đủ;
- `result > 0`: `left` đứng **sau** `right`.

**Không suy ra `compareTo()` luôn trả đúng `-1`, `0` hoặc `1`**. Hợp đồng `Comparable` chỉ quy định dấu. Nếu muốn in ra `-1/0/1` trong ví dụ, dùng `Integer.signum(result)`.

Bài này giúp bạn:

1. Nắm lịch sử: `Runtime.Version` có từ **Java 9**, còn mô hình tên các thành phần **FEATURE/INTERIM/UPDATE/PATCH** và các accessor mới được làm rõ ở **Java 10** theo JEP 322.
2. Hiểu cấu trúc `$VNUM`, `$PRE`, `$BUILD`, `$OPT`.
3. Áp dụng **đúng thứ tự ưu tiên** của `compareTo()`, gồm pre-release, build number và thông tin build tùy chọn.
4. Phân biệt `compareTo()` với `compareToIgnoreOptional()` và `equals()` với `equalsIgnoreOptional()`.
5. Sắp xếp đúng, dùng `TreeSet`/`TreeMap` cẩn thận khi comparator không nhất quán với `equals`.
6. Parse hợp lệ và từ chối các chuỗi sai dạng, đặc biệt hậu tố số 0 và phiên bản kiểu Java 8 cũ.
7. Viết chương trình Java chạy được để kiểm thử phiên bản thật, ngưỡng yêu cầu, dữ liệu pre-release và build.

**Special Note:** chỉ dùng API và quy tắc vẫn áp dụng trên Java hiện đại. Không khuyến khích các accessor `major()/minor()/security()` đã deprecated; thay bằng `feature()/interim()/update()/patch()`.

## 2. Phân biệt phiên bản JDK với kiểu version bất kỳ

`Runtime.Version` là **mô hình phiên bản dành cho Java SE Platform/JDK**, theo phiên bản cấu trúc được JDK quy định. Nó **không** phải một thư viện so sánh Semantic Versioning (SemVer) bất kỳ, không phải Maven `ComparableVersion` và cũng không phải công cụ so sánh mọi nhãn release của hệ điều hành hoặc sản phẩm.

Ví dụ có ý nghĩa trong lớp này:

```text
10
17
17.0.1
17.0.10+7
17.0.10+7-LTS
21-ea+12
21+-vendor
```

**Không giả định** một chuỗi sản phẩm tùy ý như `1.8.0_202`, `v21.0.1`, `21.0.0` hay `21.0.1-rc.1+meta` được `Runtime.Version.parse` chấp nhận hoặc có ý nghĩa tương đương phiên bản của JDK.

### 2.1. Vì sao cần API riêng?

So sánh chuỗi thuần có thể cho kết quả sai:

```java
boolean wrong =
        "17.0.10".compareTo("17.0.2") < 0; // true

boolean correct =
        Runtime.Version.parse("17.0.10")
            .compareTo(Runtime.Version.parse("17.0.2")) > 0; // true
```

Đây là mảnh code đặt trong method. `String.compareTo` so sánh lexicographic: ký tự `'1'` trong `"10"` xuất hiện trước `'2'`, nên chuỗi `"17.0.10"` nhỏ hơn `"17.0.2"`. `Runtime.Version` thì hiểu từng thành phần numeric, do đó `10 > 2`.

Thêm vấn đề: chữ `ea` đánh dấu *early access*, build `+7`, thông tin `-LTS`... đều có quy tắc so sánh riêng; không thể xử lý đúng bằng `split("\\.")` rồi so sánh toàn bộ chuỗi còn lại như text.

## 3. Bối cảnh Java 9 và Java 10

Lớp `Runtime.Version` và `Runtime.Version.parse(String)` được giới thiệu cùng mô hình phiên bản JDK 9 (JEP 223). Java 10 tinh chỉnh thành mô hình dựa trên nhịp phát hành (JEP 322), thay tên gọi các số đầu thành:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
```

| Thành phần | Ý nghĩa trong mô hình Java 10+ | API |
|---|---|---|
| `FEATURE` | Số tăng ở mỗi feature release | `feature()` |
| `INTERIM` | Số cho interim release, thường là 0 theo lịch phát hành sáu tháng | `interim()` |
| `UPDATE` | Số tăng ở update release | `update()` |
| `PATCH` | Số cho emergency patch release | `patch()` |
| Các phần tử thứ năm trở đi | Có thể dành cho bản vá đặc thù của downstream implementor | `version()` |

Ví dụ `17.0.10` có `FEATURE=17`, `INTERIM=0`, `UPDATE=10` và `PATCH=0` vì thành phần cuối không có trong chuỗi. `patch()` trả 0 nếu vắng mặt.

Các API kiểu `major()`, `minor()`, `security()` được giữ để tương thích nhưng **deprecated từ Java 10**, vì tên gọi cũ không còn phản ánh chuẩn phát hành. Trong mã mới, hãy đọc `feature()`, `interim()`, `update()` và `patch()`.

**Quan trọng:** `Runtime.Version` là class có từ Java 9; bài học không khẳng định Java 10 mới tạo ra `compareTo()`. Ý nghĩa trong phạm vi Java 10 là hiểu đúng mô hình phiên bản đã được tinh chỉnh và áp dụng `compareTo` với các thành phần đúng.

## 4. Cấu trúc một chuỗi phiên bản hợp lệ

Theo Javadoc, chuỗi phiên bản gồm **version number** và các phần thông tin tùy chọn:

```text
$VNUM(-$PRE)?+$BUILD(-$OPT)?
$VNUM-$PRE(-$OPT)?
$VNUM(+- $OPT)  // xem lưu ý ngay dưới
```

Dòng cuối trong sơ đồ được đặt khoảng trắng để dễ thấy các token. **Cú pháp thật, không có khoảng trắng** của trường hợp chỉ có optional metadata là `$VNUM+-$OPT`, ví dụ `17+-vendor`.

Trong thực tế:

```text
17.0.10+7-LTS
|_____| | |___|
 VNUM  |  OPT = LTS
        BUILD = 7

21-ea+12
|_||_||_|
VNUM PRE BUILD

21+-vendor
|_|  |_____|
VNUM   OPT (không có BUILD)
```

### 4.1. `$VNUM` — dãy các số có dấu chấm

Một số phiên bản là dãy **không rỗng** của các số nguyên không âm ngăn bởi dấu chấm:
- Phần tử đầu **không bằng 0**;
- Không cho phép số có **leading zeros** kiểu `01`;
- **Phần tử cuối không được là 0**;
- Những số 0 ở giữa vẫn được phép khi cần bước tới thành phần phía sau.

Ví dụ:

| Chuỗi | Hợp lệ? | Giải thích |
|---|---|---|
| `17` | Có | Chỉ một FEATURE |
| `17.0.1` | Có | INTERIM=0, UPDATE=1 |
| `17.0.10` | Có | UPDATE=10 |
| `17.0.10.1` | Có | PATCH=1 |
| `17.0` | **Không** | Phần tử cuối là 0 |
| `17.0.0` | **Không** | Phần tử cuối là 0 |
| `17.01` | **Không** | Leading zero |
| `0` | **Không** | FEATURE phải bắt đầu khác 0 |
| `17.0.0.1` | Có | Số 0 nằm ở giữa, PATCH=1 |

Không nên tạo phiên bản `17.0.0` theo thói quen SemVer, vì JDK version scheme yêu cầu **bỏ các thành phần zero ở cuối**. Đây là khác biệt quan trọng khi viết parser hoặc nhận phiên bản từ cấu hình.

### 4.2. `$PRE` — pre-release identifier

`$PRE` thường là `ea` (early access) hoặc `internal`, nhưng cú pháp cho phép chữ/số theo Javadoc. Ví dụ:

```text
21-ea
21-ea+12
21-2
21-10
```

`21-ea` là phiên bản **trước** bản không có PRE là `21`. Số `2` và `10` trong PRE được so sánh **theo số**. Cách so sánh pre-release **không** phải chỉ đơn giản gọi `String.compareTo` cho mọi trường hợp.

### 4.3. `$BUILD` — build number

`$BUILD` là số build không âm; ví dụ:

```text
21+1
21+12
21-ea+12
21.0.1+10
```

Khi cùng phiên bản số và cùng PRE, build lớn hơn đứng sau build nhỏ hơn. Khi **chỉ một phía có BUILD**, phía có BUILD được coi **lớn hơn** phía không có BUILD theo `compareTo`.

Đây là một điểm dễ nhầm với **SemVer 2.0**: SemVer thường không dùng build metadata để thay đổi precedence, nhưng `Runtime.Version.compareTo` **có so sánh BUILD**.

### 4.4. `$OPT` — thông tin build bổ sung

`$OPT` là thông tin nhận diện bổ sung như `LTS`, `vendor` hoặc nhãn build theo implementor:

```text
17.0.10+7-LTS
17.0.10+7-Vendor
17+-vendor
```

`optional()` trả `Optional<String>` tương ứng. `OPT` được so sánh **lexicographically** khi sử dụng `compareTo()` và các thành phần trước đó bằng nhau.

Cần hiểu `LTS` trong `OPT` là **nhãn**, không phải cam kết tự động rằng binary đang chạy chắc chắn có một gói hỗ trợ dài hạn hoặc cập nhật bảo mật từ nhà cung cấp. Quyền hỗ trợ và vòng đời sản phẩm phải được xác minh theo vendor/distribution.

## 5. Quy tắc `compareTo()` — thứ tự ưu tiên từ cao xuống thấp

Theo hợp đồng `Runtime.Version.compareTo(Runtime.Version)`, thứ tự so sánh là:

1. **Dãy các thành phần số (`VNUM`)**;
2. **Pre-release identifier (`PRE`)**;
3. **Build number (`BUILD`)**;
4. **Thông tin build bổ sung (`OPT`)**.

Khi tìm được thành phần **khác nhau đầu tiên**, kết quả được quyết định tại đó. Các phần sau **không thể đảo ngược** sự khác biệt ở phần ưu tiên cao hơn.

| Ưu tiên | Cặp ví dụ | Kết quả | Lý do |
|---|---|---|---|
| 1 — VNUM | `17.0.2` vs `17.0.10` | `17.0.2 < 17.0.10` | So sánh 2 và 10 theo số |
| 1 — VNUM | `17+999` vs `17.0.1` | `17+999 < 17.0.1` | Update 1 ưu tiên hơn BUILD 999 |
| 2 — PRE | `17-ea` vs `17` | `17-ea < 17` | Có PRE thì nhỏ hơn bản GA không có PRE |
| 2 — PRE | `17-2` vs `17-10` | `17-2 < 17-10` | PRE toàn chữ số được so sánh theo số |
| 2 — PRE | `17-10` vs `17-ea` | `17-10 < 17-ea` | PRE dạng số nhỏ hơn PRE không phải số |
| 3 — BUILD | `17` vs `17+1` | `17 < 17+1` | Không BUILD được coi nhỏ hơn có BUILD |
| 3 — BUILD | `17+1` vs `17+2` | `17+1 < 17+2` | BUILD so sánh theo số |
| 4 — OPT | `17+1` vs `17+1-LTS` | `17+1 < 17+1-LTS` | Không OPT được coi nhỏ hơn có OPT |
| 4 — OPT | `17+1-LTS` vs `17+1-vendor` | `17+1-LTS < 17+1-vendor` | OPT so sánh từ điển, có phân biệt chữ hoa/thường |

Những kết luận trên nói về **thứ tự theo cấu trúc phiên bản JDK**, không phải độ an toàn, bảo mật hay mức khuyến nghị dùng của từng binary. Chẳng hạn một nhãn `LTS` lexicographically lớn hơn nhãn khác **không có nghĩa** binary được hỗ trợ tốt hơn.

### 5.1. So sánh số thành phần `VNUM`

Các thành phần số được so sánh theo từng vị trí **từ trái sang phải**. Ví dụ:

```text
17.0.2  <  17.0.10
      2 <       10

17.0.10 < 17.1
    0   <    1      (INTERIM quyết định trước UPDATE)
```

Nếu một dãy ngắn hơn một dãy khác, các thành phần còn thiếu của dãy ngắn hơn được coi là **nhỏ hơn** các thành phần tương ứng của dãy dài hơn, theo Javadoc.

**Không thêm các số 0 cuối** để “làm đẹp” trước khi parse; JDK version scheme cấm `17.0` và `17.0.0`. Nếu muốn lấy bốn trường cố định cho logic khác, đọc `feature()`/`interim()`/`update()`/`patch()` sau khi đã parse hợp lệ.

### 5.2. So sánh `PRE`

Có ba trường hợp:

1. Một phiên bản có `PRE`, phiên bản kia không có: phiên bản **có PRE nhỏ hơn**.
2. Cả hai PRE chỉ chứa chữ số: so sánh **numerically**.
3. Một PRE số, một PRE không phải số: PRE **số nhỏ hơn**.
4. Cả hai không phải số: so sánh **lexicographically**.

Thứ tự này không phải thứ tự ngữ nghĩa của mọi nhãn alpha/beta/rc theo SemVer. Nếu ứng dụng cần quy tắc độc lập kiểu `alpha < beta < rc` cho phiên bản sản phẩm, `Runtime.Version` có thể không phải công cụ phù hợp.

### 5.3. So sánh `BUILD`

Nếu các phần trước bằng nhau:
- Không BUILD < có BUILD;
- Cùng có BUILD → so sánh số build;
- Không nên suy `+999` có thể làm một `VNUM` thấp hơn vượt qua một `VNUM` cao hơn.

Ví dụ `17+999` vẫn nhỏ hơn `17.0.1` dù 999 > 1, vì so sánh **VNUM trước BUILD**.

### 5.4. So sánh `OPT`

Nếu `VNUM`, `PRE` và `BUILD` bằng nhau:
- Không OPT < có OPT;
- Hai chuỗi OPT được so sánh **lexicographically**;
- `compareToIgnoreOptional()` **bỏ qua đúng trường OPT**, không bỏ qua BUILD.

Ví dụ:

```text
17.0.10+7-LTS
17.0.10+7-Vendor
```

`compareTo` phân biệt hai version do `OPT` khác nhau. `compareToIgnoreOptional` trả 0 vì phần cấu trúc khác nhau duy nhất đã bị bỏ qua.

## 6. Chương trình đầy đủ 1 — kiểm tra từng quy tắc so sánh

Lưu tệp **`VersionOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class VersionOrderDemo {

    // In ra -1, 0, +1; không phụ thuộc trị tuyệt đối của compareTo().
    static int sign(String left, String right) {
        return Integer.signum(Runtime.Version.parse(left)
                .compareTo(Runtime.Version.parse(right)));
    }

    public static void main(String[] args) {
        System.out.println("numeric=" +
                sign("17.0.2", "17.0.10"));
        System.out.println("preVsGA=" +
                sign("17-ea", "17"));
        System.out.println("numericPre=" +
                sign("17-2", "17-10"));
        System.out.println("numericVsAlphaPre=" +
                sign("17-10", "17-ea"));
        System.out.println("buildAbsent=" +
                sign("17", "17+1"));
        System.out.println("optionalAbsent=" +
                sign("17+1", "17+1-LTS"));
        System.out.println("versionBeforeBuild=" +
                sign("17.0.1", "17+999"));
        System.out.println("optionalLexical=" +
                sign("17+1-LTS", "17+1-vendor"));

        var versions = new ArrayList<Runtime.Version>();

        for (String text : List.of(
                "18", "17.0.1", "17+1-LTS", "17", "17+1",
                "17-ea", "17+-vendor")) {
            versions.add(Runtime.Version.parse(text));
        }

        versions.sort(Comparator.naturalOrder());
        System.out.println("sorted=" + versions);
    }
}
```

Biên dịch và chạy bằng JDK có hỗ trợ target Java 10:

```bash
javac --release 10 VersionOrderDemo.java
java VersionOrderDemo
```

Hoặc trong dự án Java 17+:

```bash
javac --release 17 VersionOrderDemo.java
java VersionOrderDemo
```

**Stdout chính xác đã kiểm thử:**

```text
numeric=-1
preVsGA=-1
numericPre=-1
numericVsAlphaPre=-1
buildAbsent=-1
optionalAbsent=-1
versionBeforeBuild=1
optionalLexical=-1
sorted=[17-ea, 17, 17+-vendor, 17+1, 17+1-LTS, 17.0.1, 18]
```

### 6.1. Đọc kết quả

- `numeric=-1`: update 2 trước update 10, dù thứ tự chuỗi `String.compareTo` có thể sai.
- `preVsGA=-1`: bản `17-ea` đứng trước `17` không có PRE.
- `numericPre=-1`: identifier `2` nhỏ hơn `10` theo số.
- `numericVsAlphaPre=-1`: identifier toàn chữ số đứng trước identifier chữ `ea`.
- `buildAbsent=-1`: `17` đứng trước `17+1` nếu so sánh đầy đủ.
- `optionalAbsent=-1`: `17+1` đứng trước `17+1-LTS`.
- `versionBeforeBuild=1`: phía `17.0.1` **lớn hơn** `17+999`; thứ tự `VNUM` quyết định trước BUILD.
- `optionalLexical=-1`: `LTS` đứng trước `vendor` theo lexical ordering.
- Danh sách `sorted` cho thấy kết quả **tổng thể** trên một tập có PRE, OPT, BUILD và UPDATE khác nhau.

**Tại sao có `17+-vendor` trong danh sách?** Đây là cú pháp hợp lệ để có **OPT nhưng không có BUILD**. Nó đứng sau `17` (do có OPT), nhưng trước `17+1` (do không có BUILD). Không nhầm `17+-vendor` với `17-ea`: ký tự `+` có ý nghĩa cấu trúc riêng.

## 7. `compareToIgnoreOptional()` bỏ qua chính xác điều gì?

Phương thức:

```java
int result = left.compareToIgnoreOptional(right);
```

bỏ qua **thành phần `$OPT`**, tức chuỗi thông tin build bổ sung từ `optional()`. Nó **vẫn so sánh**:
- Dãy `VNUM`;
- `PRE`;
- **BUILD number**.

Ví dụ:

| Vế trái | Vế phải | `compareTo` | `compareToIgnoreOptional` |
|---|---|---|---|
| `17+7-LTS` | `17+7-Vendor` | Khác 0 | **0** |
| `17+7-LTS` | `17+8-Vendor` | Nhỏ hơn 0 | Nhỏ hơn 0 |
| `17-ea+7-LTS` | `17+7-LTS` | Nhỏ hơn 0 | Nhỏ hơn 0 |
| `17+-foo` | `17` | Lớn hơn 0 | **0** |
| `17.0.1+7-LTS` | `17+7-LTS` | Lớn hơn 0 | Lớn hơn 0 |

**Không được hiểu** `compareToIgnoreOptional()` là “so sánh chỉ FEATURE”, “bỏ qua mọi build” hoặc “bỏ qua pre-release”. Tên `Optional` ở đây là thành phần `$OPT`, không phải kiểu `java.util.Optional` hay toàn bộ các phần tùy chọn của chuỗi.

### 7.1. Dùng khi nào?

- Muốn so sánh hai bản JDK có cùng version number, PRE và BUILD nhưng nhãn vendor khác nhau;
- Muốn sắp xếp release theo một hợp đồng **không quan tâm nhãn build bổ sung**;
- Muốn so khớp một ngưỡng phiên bản đã được phê duyệt mà không muốn `$OPT` tạo khác biệt.

Ngược lại, nếu đang quản lý bản cài của nhiều nhà cung cấp và cần phân biệt chính xác cả build metadata để truy vết hoặc rollback, `compareTo()` có thể thích hợp hơn.

**Quan trọng:** cả hai phương thức chỉ cung cấp một **thứ tự kỹ thuật**. Chúng không quyết định binary nào an toàn hơn, có hỗ trợ LTS thật, có patch bảo mật được backport hoặc tương thích với một thư viện cụ thể.

## 8. `equals()` và `equalsIgnoreOptional()`

Cặp phương thức equality tương ứng:

```java
boolean exact = left.equals(right);
boolean withoutOptional = left.equalsIgnoreOptional(right);
```

- `equals` phân biệt phiên bản đầy đủ, gồm `$OPT`;
- `equalsIgnoreOptional` xem hai phiên bản bằng nhau khi bỏ qua `$OPT`;
- `compareTo` và `equals` nên được sử dụng **cùng một chính sách**;
- `compareToIgnoreOptional` và `equalsIgnoreOptional` là cặp nhất quán với nhau.

**Không** dùng `equalsIgnoreOptional` để suy rằng hash code của hai instance nhất định bằng nhau. `hashCode()` tuân theo `equals` đầy đủ, không phải theo mọi phép so sánh tùy biến bỏ qua metadata.

### 8.1. Quy tắc quan trọng cho `TreeSet` và `TreeMap`

Với các collection có thứ tự như `TreeSet` và `TreeMap`, **comparator quyết định tính tương đương của key/phần tử**. Nếu chọn comparator `Runtime.Version::compareToIgnoreOptional`, các phiên bản chỉ khác `$OPT` có thể **bị coi là trùng** trong những collection đó.

Đây có thể là yêu cầu đúng (gom các nhãn vendor), nhưng cũng có thể làm mất bản ghi cần quản lý riêng.

Với `HashSet`/`HashMap`, phép trùng key dựa trên `equals` và `hashCode`, nên **không** có cơ chế tự động bỏ qua `$OPT` chỉ vì bạn đã từng gọi `equalsIgnoreOptional`. Không trộn chính sách giữa hai loại collection mà không hiểu hệ quả.

## 9. Chương trình đầy đủ 2 — equality, BUILD/OPT và sorted set

Lưu tệp **`VersionOptionalDemo.java`**:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class VersionOptionalDemo {
    public static void main(String[] args) {
        Runtime.Version a =
                Runtime.Version.parse("17.0.10+7-LTS");
        Runtime.Version b =
                Runtime.Version.parse("17.0.10+7-Vendor");

        System.out.println("fullCompare=" +
                Integer.signum(a.compareTo(b)));
        System.out.println("ignoreOptionalCompare=" +
                Integer.signum(a.compareToIgnoreOptional(b)));
        System.out.println("fullEquals=" + a.equals(b));
        System.out.println("ignoreOptionalEquals=" +
                a.equalsIgnoreOptional(b));

        System.out.println("feature=" + a.feature());
        System.out.println("interim=" + a.interim());
        System.out.println("update=" + a.update());
        System.out.println("patch=" + a.patch());
        System.out.println("versionComponents=" + a.version());
        System.out.println("prePresent=" + a.pre().isPresent());
        System.out.println("build=" + a.build().orElse(-1));
        System.out.println("optional=" +
                a.optional().orElse("none"));

        var natural = new TreeSet<Runtime.Version>();
        natural.add(a);
        natural.add(b);

        var ignoringOptional = new TreeSet<Runtime.Version>(
                Runtime.Version::compareToIgnoreOptional);
        ignoringOptional.add(a);
        ignoringOptional.add(b);

        System.out.println("naturalSetSize=" + natural.size());
        System.out.println("ignoreOptionalSetSize=" +
                ignoringOptional.size());

        System.out.println("runtimeApiFeatureAtLeast10=" +
                (Runtime.version().feature() >= 10));
    }
}
```

Lệnh:

```bash
javac --release 10 VersionOptionalDemo.java
java VersionOptionalDemo
```

**Stdout trên JDK hiện đại có FEATURE ít nhất 10:**

```text
fullCompare=-1
ignoreOptionalCompare=0
fullEquals=false
ignoreOptionalEquals=true
feature=17
interim=0
update=10
patch=0
versionComponents=[17, 0, 10]
prePresent=false
build=7
optional=LTS
naturalSetSize=2
ignoreOptionalSetSize=1
runtimeApiFeatureAtLeast10=true
```

Dòng cuối phụ thuộc vào **runtime đang chạy**; khi dùng Java 10 hoặc mới hơn, nó là `true`. Nếu chạy trên JDK khác không đáp ứng điều kiện, code cần xử lý theo yêu cầu thực tế; không coi số 17 ở ví dụ đã parse là phiên bản thật của JVM.

### 9.1. Giải thích kết quả equality

- `a` và `b` cùng `17.0.10`, cùng BUILD `7`, chỉ khác OPT `LTS` và `Vendor`.
- `compareTo`: `LTS` nhỏ hơn `Vendor` trong lexical ordering nên `fullCompare=-1`.
- `compareToIgnoreOptional`: bỏ phần khác biệt OPT nên bằng 0.
- `equals`: `false` vì phiên bản đầy đủ khác nhau.
- `equalsIgnoreOptional`: `true` vì bỏ qua OPT thì giống nhau.

### 9.2. Giải thích các getter

- `feature=17` là phần đầu;
- `interim=0` là phần thứ hai;
- `update=10` là phần thứ ba;
- `patch=0` vì không có patch element;
- `versionComponents=[17, 0, 10]` là dãy **thực có trong số phiên bản**, không tự bổ sung zero cuối thành phần thứ tư.
- `prePresent=false` vì không có `-ea` hoặc pre-release identifier khác.
- `build=7` là số lấy qua `Optional<Integer>`;
- `optional=LTS` là chuỗi metadata lấy qua `Optional<String>`.

`version()` trả một `List<Integer>` **unmodifiable**. Không sửa trực tiếp danh sách đó để thay phiên bản; tạo/parse một `Runtime.Version` mới từ version string hợp lệ nếu cần.

### 9.3. Vì sao TreeSet còn một phần tử?

`naturalSetSize=2`: theo `compareTo` đầy đủ, hai giá trị khác nhau.

`ignoreOptionalSetSize=1`: comparator xem chúng bằng nhau khi chỉ khác OPT; `TreeSet` giữ một phần tử đại diện. **Không coi đây là bug Java**. Đây là hệ quả của việc chọn thứ tự tương đương với `equalsIgnoreOptional`, nhưng **không đồng nhất** với `equals` đầy đủ.

Nếu ứng dụng quản lý nhiều bản build của nhiều vendor và không được phép mất bản, hãy giữ `compareTo` tự nhiên hoặc một key rõ ràng chứa vendor/build metadata. Nếu ứng dụng chỉ muốn một bản đại diện cho mỗi release/build cơ bản, phải xác định policy chọn đại diện và báo trùng có chủ đích, thay vì dựa vào phần tử được thêm đầu tiên mà không ghi nhận.

### 9.4. Vì sao phải tránh tính hash từ `equalsIgnoreOptional`?

Một hash key phải dùng chính sách equality/hash nhất quán. `Runtime.Version.hashCode()` được thiết kế cho `equals` đầy đủ. Nếu muốn tra cứu theo phiên bản **bỏ qua OPT**, hãy định nghĩa một key canonical riêng phản ánh VNUM/PRE/BUILD hoặc một comparator/collection phù hợp, thay vì hy vọng `HashSet` tự dùng `equalsIgnoreOptional`.

## 10. Parse và validate phiên bản trước khi so sánh

API:

```java
Runtime.Version version = Runtime.Version.parse(text);
```

`parse` đòi chuỗi tuân theo định dạng phiên bản JDK. Nếu không hợp lệ, nó ném `IllegalArgumentException`. Khi input là `null`, cần xử lý `NullPointerException` theo hợp đồng API/thư viện thay vì để input không được xác thực đi qua.

Những lỗi thường gặp:

1. **Hậu tố 0:** `17.0`, `17.0.0` không hợp lệ.
2. **Tên Java 8 cũ:** `1.8.0_202` không phải chuỗi kiểu JEP 322.
3. **Thêm tiền tố chữ tùy ý:** `v17.0.10` không tự động là một JDK version string.
4. **Build/metadata sai cấu trúc:** `+BUILD` phải là số hợp lệ; không phải mọi chuỗi SemVer `+metadata` có thể dùng trực tiếp.
5. **Số quá lớn/không parse được:** các phần tử có giới hạn biểu diễn của API; cần báo lỗi cấu hình thay vì ép về một số bất kỳ.
6. **Dùng `split("\\.")` để parse mọi phần:** sẽ làm sai trường hợp có `-ea`, `+7` hoặc `-LTS`.

### 10.1. Không đổi dữ liệu không hợp lệ thành phiên bản giả

Ví dụ chống mẫu:

```java
try {
    return Runtime.Version.parse(configuredVersion);
} catch (IllegalArgumentException ignored) {
    return Runtime.Version.parse("1");
}
```

Đây là mảnh code giả định method trả `Runtime.Version`. Nếu lỗi cấu hình là vấn đề nghiêm trọng, fallback về `1` có thể che nguyên nhân và khiến bộ kiểm tra tương thích hành xử sai. Hãy báo rõ input nào không hợp lệ và yêu cầu cấu hình theo version scheme thực sự được chấp nhận.

Nếu một hệ thống cần hỗ trợ cả legacy `1.8.0_202`, có thể xây **adapter chuyển đổi được kiểm thử theo quy tắc rõ ràng** hoặc dùng một version parser hỗ trợ format đó, nhưng **không** ép `Runtime.Version.parse` phải hiểu tất cả.

## 11. Chương trình đầy đủ 3 — kiểm tra parse và ngưỡng tối thiểu

Lưu tệp **`VersionValidationDemo.java`**:

```java
import java.util.List;

public class VersionValidationDemo {

    static boolean valid(String text) {
        try {
            Runtime.Version.parse(text);
            return true;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    static boolean minimum(
            Runtime.Version current,
            Runtime.Version required) {
        return current.compareToIgnoreOptional(required) >= 0;
    }

    public static void main(String[] args) {
        System.out.println("valid17Update=" +
                valid("17.0.10+7"));
        System.out.println("valid17Ea=" +
                valid("17-ea+3"));
        System.out.println("trailingZeroRejected=" +
                !valid("17.0"));
        System.out.println("allTrailingZeroRejected=" +
                !valid("17.0.0"));
        System.out.println("legacyFormatRejected=" +
                !valid("1.8.0_202"));

        var required = Runtime.Version.parse("17");
        System.out.println("eaBelowGa=" +
                !minimum(Runtime.Version.parse("17-ea"),
                         required));
        System.out.println("updateAboveGa=" +
                minimum(Runtime.Version.parse("17.0.10+7-LTS"),
                        required));
        System.out.println("stable17=" +
                minimum(Runtime.Version.parse("17"), required));

        List<String> original = List.of(
                "17.0.2", "17.0.10", "17-ea");
        System.out.println("stringCompareWrong=" +
                ("17.0.10".compareTo("17.0.2") < 0));
        System.out.println("versionCompareCorrect=" +
                (Runtime.Version.parse("17.0.10")
                    .compareTo(Runtime.Version.parse("17.0.2")) > 0));
    }
}
```

```bash
javac --release 10 VersionValidationDemo.java
java VersionValidationDemo
```

**Stdout chính xác:**

```text
valid17Update=true
valid17Ea=true
trailingZeroRejected=true
allTrailingZeroRejected=true
legacyFormatRejected=true
eaBelowGa=true
updateAboveGa=true
stable17=true
stringCompareWrong=true
versionCompareCorrect=true
```

### 11.1. Ý nghĩa

- `valid17Update=true` vì `17.0.10+7` đúng format.
- `valid17Ea=true` vì `17-ea+3` có pre-release và build đúng cú pháp.
- `trailingZeroRejected=true`, `allTrailingZeroRejected=true` vì `17.0` và `17.0.0` vi phạm quy tắc `VNUM`.
- `legacyFormatRejected=true` vì `1.8.0_202` là dạng phiên bản Java cũ, không phải một `VSTR` JDK 10+.
- `eaBelowGa=true` vì `17-ea` có PRE, đứng trước bản `17` không có PRE.
- `updateAboveGa=true` và `stable17=true` vì những phiên bản này không thấp hơn ngưỡng `17`.
- Hai dòng cuối nhấn mạnh lỗi so sánh chuỗi và cách `Runtime.Version` xử lý đúng numeric components.

### 11.2. Khi nào dùng `minimum(...)` như ví dụ?

Hàm `minimum` là một ví dụ chính sách: kiểm tra **thứ tự release đầy đủ nhưng bỏ nhãn OPT**. Nó có thể dùng khi hệ thống có ngưỡng chính xác như `17.0.10+7` và không quan tâm chuỗi nhãn bổ sung.

Nhưng nếu yêu cầu **“JDK feature 17 hoặc mới hơn để dùng một Java API”**, thường việc kiểm tra:

```java
boolean featureAtLeast17 =
        Runtime.version().feature() >= 17;
```

lại rõ hơn vì nó nêu trực tiếp điều kiện **FEATURE**. Dù vậy, cần xét preview APIs, module có mặt hay không, policy hỗ trợ early-access, và yêu cầu thật của phần mềm: chỉ số FEATURE **không** bảo đảm mọi tính năng tùy chọn, native component hoặc capability của vendor được cài đặt.

Nếu yêu cầu **không được chạy trên early-access release của chính FEATURE đó**, cần thêm điều kiện release policy dựa trên `pre()` và so sánh ngưỡng GA tương ứng. `Runtime.version().feature() >= 17` có thể đúng trên `17-ea`, nhưng phiên bản `17-ea` đứng **trước** `17` theo `compareTo`.

## 12. `Runtime.version()` khác `Runtime.Version.parse(...)`

`Runtime.Version.parse("17")` tạo một đối tượng đại diện cho **chuỗi được cung cấp**, không phụ thuộc JVM nào đang chạy.

`Runtime.version()` trả phiên bản **của runtime Java hiện tại**. Ví dụ:

```java
Runtime.Version actualRuntime = Runtime.version();
System.out.println(actualRuntime.feature());
```

Đây là mảnh code độc lập trong method. **Không hard-code stdout** vì kết quả phải phù hợp JDK thực tế của máy.

Trường hợp sử dụng:
- Feature gating có chủ đích;
- Ghi diagnostic runtime để hỗ trợ điều tra lỗi;
- Kiểm tra ngưỡng tối thiểu của chương trình;
- Chọn nhánh xử lý khi thực sự phải tương thích nhiều JDK.

**Lưu ý:** `javac --release 10` ảnh hưởng API/language target ở **thời điểm biên dịch**, không khiến chương trình chạy trên JDK 24 tự nhận `Runtime.version().feature() == 10`. Biên dịch target 10 và runtime thực tế là hai thứ khác nhau.

Cần phân biệt:
- **Build target:** phiên bản ngôn ngữ/API được công cụ biên dịch cho phép.
- **Runtime version:** JVM thực tế chạy bytecode.
- **Dependency requirements:** thư viện/module bên ngoài cần phiên bản và capability cụ thể.

Đừng dùng một trong ba thông tin để suy ra hai thông tin còn lại mà không kiểm tra.

## 13. Sắp xếp phiên bản và chọn bản mới nhất

`Runtime.Version` implements `Comparable<Runtime.Version>`, do đó có thể dùng:

```java
var versions = new java.util.ArrayList<Runtime.Version>();
versions.add(Runtime.Version.parse("17.0.2"));
versions.add(Runtime.Version.parse("17.0.10"));
versions.add(Runtime.Version.parse("17-ea"));

versions.sort(java.util.Comparator.naturalOrder());
```

Đây là mảnh code trong phương thức. Danh sách theo comparator tự nhiên sẽ là `[17-ea, 17.0.2, 17.0.10]`, vì `PRE` và UPDATE được so sánh đúng thứ tự.

Khi muốn lấy phần tử cuối của danh sách đã sắp xếp, cần làm rõ “mới nhất” là:
- Lớn nhất theo **version ordering**;
- Hay **bản có bản vá bảo mật được backport mới nhất**;
- Hay **bản được vendor hỗ trợ**;
- Hay **build mới nhất của cùng nhánh LTS**.

`compareTo` chỉ trả lời câu hỏi thứ nhất. Nó **không** đọc dữ liệu bảo mật, ngày phát hành thật, chính sách vendor hoặc trạng thái support.

### 13.1. Lưu ý comparator trong Map/Set

`TreeSet<Runtime.Version>` dùng comparator để xác định phần tử trùng. Nếu dùng:

```java
var set = new java.util.TreeSet<Runtime.Version>(
        Runtime.Version::compareToIgnoreOptional);
```

hai phiên bản chỉ khác OPT có thể bị coi là một. Đối với `TreeMap` cũng vậy: key mà comparator trả 0 được xem là key tương đương, có nguy cơ ghi đè bản ghi.

Nếu cần vừa giữ tất cả vendor builds vừa nhóm theo VNUM/PRE/BUILD:
- Giữ full version làm key chính;
- Dùng một **group key** riêng cho policy bỏ OPT;
- Hoặc dùng cấu trúc `Map<GroupKey, List<BuildInfo>>` theo domain.

Đừng dựa vào thứ tự thêm ngẫu nhiên để chọn một bản đại diện. Nếu cần một bản duy nhất, hãy xác định policy ưu tiên vendor/build rõ ràng.

### 13.2. Không lấy `compareTo` làm ID định danh nhà cung cấp

Hai binary cùng version number/build string vẫn có thể được đóng gói bởi các nhà cung cấp khác nhau và có thành phần khác nhau. `Runtime.Version` không chứa đầy đủ mọi metadata về vendor, hệ điều hành, kiến trúc, flag biên dịch hoặc module. Khi quản lý cài đặt, hãy dùng thêm những thông tin cần thiết; version ordering chỉ là một phần của identity.

## 14. Vì sao SemVer không hoàn toàn giống Java Runtime.Version?

Mặc dù cả hai có các thành phần số, pre-release và metadata, **quy tắc không hoàn toàn giống nhau**:

| Nội dung | `Runtime.Version` cho JDK | SemVer 2.0 |
|---|---|---|
| Các số chính | `FEATURE.INTERIM.UPDATE.PATCH` và có thể hơn bốn thành phần | `MAJOR.MINOR.PATCH` |
| Số 0 cuối | Không cho `17.0`, `17.0.0` là `VNUM` hợp lệ | SemVer cần đủ ba số chính, ví dụ `17.0.0` |
| Pre-release | PRE là một identifier; số so sánh numeric, số nhỏ hơn nonnumeric | Có dãy dot-separated pre-release identifiers với quy tắc riêng |
| Build | `+BUILD` là **số** và được so sánh trong `compareTo` | Build metadata sau `+` không ảnh hưởng precedence |
| Optional metadata | `$OPT` có thể theo sau build hoặc ở dạng `+-OPT` | Build metadata khác theo cú pháp và semantics |
| Mục tiêu | Version strings của Java SE/JDK | Versioning sản phẩm/phần mềm theo SemVer |

Vì vậy không nên parse mọi chuỗi `"1.2.3-rc.1+meta"` bằng `Runtime.Version.parse` hoặc lấy comparator này áp dụng cho dependency versions tùy ý.

Đặc biệt, trong SemVer `1.2.3+build.7` và `1.2.3+build.8` có **precedence như nhau**. Trong `Runtime.Version`, `17+7` và `17+8` **khác thứ tự**, vì BUILD là số được so sánh.

**Đúng công cụ cho đúng hệ phiên bản:** dùng `Runtime.Version` cho chuỗi JDK theo chuẩn, dùng comparator/version library được định nghĩa cho Maven/Gradle/SemVer hoặc hệ sản phẩm khi đó mới là yêu cầu.

## 15. Các vấn đề biên cần kiểm tra

### 15.1. `null` và ngoại lệ

`compareTo(null)` hoặc `compareToIgnoreOptional(null)` ném `NullPointerException` theo Javadoc. Không coi null là một phiên bản thấp nhất hoặc chuỗi rỗng trừ khi ứng dụng đã định nghĩa quy tắc rõ ràng.

Ví dụ trong method:

```java
Runtime.Version current = Runtime.version();
if (requiredVersion == null) {
    throw new IllegalArgumentException("requiredVersion is missing");
}
boolean compatible =
        current.compareToIgnoreOptional(requiredVersion) >= 0;
```

Đây là mảnh code giả định `requiredVersion` kiểu `Runtime.Version`. Việc validate input trước khi gọi giúp thông điệp nghiệp vụ rõ ràng hơn.

### 15.2. Giá trị trả về của `compareTo()`

Đừng viết:

```java
if (a.compareTo(b) == 1) {
    // Sai khi coi +1 là mọi trường hợp "greater".
}
```

Thay bằng:

```java
if (a.compareTo(b) > 0) {
    // a đứng sau b theo version ordering.
}
```

Các mảnh code giả định `a`, `b` là `Runtime.Version`. Nếu cần số cố định cho test/demo, `Integer.signum(a.compareTo(b))`.

### 15.3. Bản pre-release không phải GA

`17-ea` nhỏ hơn `17`, dù cả hai có `feature() == 17`. Nếu hệ thống không cho phép EA, hãy kiểm tra `pre()` hoặc dùng phép so sánh với bản GA ngưỡng theo policy.

### 15.4. Build number là con số, không phải bản cập nhật bảo mật

`17+40` không tự động “an toàn hơn” `17.0.10+7`, chỉ vì build 40 lớn hơn 7. `VNUM` được so sánh trước. Build number thường mô tả build trong một chuỗi phát hành; đánh giá CVE/backport/security patches đòi hỏi dữ liệu vendor/distribution riêng.

### 15.5. `LTS` và các chuỗi OPT không phải phép xác minh support

`optional().orElse("none")` có thể trả `LTS`. Nhưng không dùng riêng chuỗi đó để quyết định hợp đồng hỗ trợ, cấp giấy phép hoặc tần suất cập nhật, vì vendor có thể áp dụng cách ghi metadata khác nhau.

### 15.6. Version là value-based class

`Runtime.Version` được Javadoc mô tả là **value-based**. Không dùng identity-sensitive operations như `==` để thay `equals`, không đồng bộ `synchronized(version)` và không dựa vào `System.identityHashCode(version)`. Sử dụng các phép so sánh/equality do API cung cấp.

## 16. Kiểm thử các quy tắc so sánh

Một bộ test phù hợp cần cover **mọi tầng ưu tiên**:

| Trường hợp | Điều cần assert |
|---|---|
| Numeric update `17.0.2` vs `17.0.10` | Kết quả âm |
| PRE vs GA `17-ea` vs `17` | Kết quả âm |
| PRE numeric `17-2` vs `17-10` | Kết quả âm |
| PRE numeric vs alpha `17-10` vs `17-ea` | Kết quả âm |
| BUILD absent vs present | `17 < 17+1` |
| OPT absent vs present | `17+1 < 17+1-LTS` |
| VNUM dominates build | `17.0.1 > 17+999` |
| Full vs ignore OPT | Một phép khác 0, một phép bằng 0 |
| `equals` vs `equalsIgnoreOptional` | Khác nhau khi chỉ OPT khác |
| Invalid trailing zeros | `parse("17.0")` ném `IllegalArgumentException` |
| Legacy format | `parse("1.8.0_202")` bị từ chối |
| Null compare | `compareTo(null)` ném `NullPointerException` |
| Sorted collection | Comparator bỏ OPT có thể thu gọn key |

### 16.1. Test Java thuần, không cần JUnit

Ví dụ method kiểm tra dấu (mảnh code trong class):

```java
static void assertLess(String a, String b) {
    var left = Runtime.Version.parse(a);
    var right = Runtime.Version.parse(b);
    if (left.compareTo(right) >= 0) {
        throw new AssertionError(a + " must be before " + b);
    }
}
```

Gọi:

```java
assertLess("17.0.2", "17.0.10");
assertLess("17-ea", "17");
assertLess("17+1", "17+1-LTS");
```

Đây là mảnh code cần đặt trong class cùng method; không phải file độc lập. Với JUnit 5, có thể sử dụng `assertTrue(left.compareTo(right) < 0)`, `assertEquals(0, left.compareToIgnoreOptional(right))`, hoặc `assertThrows(IllegalArgumentException.class, () -> Runtime.Version.parse("17.0"))`.

Đừng kiểm tra **nguyên chuỗi message** của exception mặc định, vì đó không phải phần bắt buộc giữ nguyên qua mọi bản JDK.

### 16.2. Kiểm tra comparator có tính nhất quán

Nếu tự viết comparator để ưu tiên nhãn vendor, pre-release hoặc capability, cần kiểm thử:
- Tính phản đối xứng của dấu;
- Tính bắc cầu;
- Quy tắc nhận diện bản bằng nhau;
- Không phụ thuộc dữ liệu mutable;
- Có hay không nhất quán với `equals` nếu dùng trong sorted set/map.

Nếu comparator trả 0 cho hai object mà `equals` thấy khác, hãy chấp nhận có chủ đích hệ quả trong `TreeSet/TreeMap`, hoặc dùng một key khác.

## 17. Lỗi phổ biến và cách sửa

| Lỗi | Cách làm đúng |
|---|---|
| So sánh `String.compareTo` với `"17.0.10"` và `"17.0.2"` | Parse và dùng `Runtime.Version.compareTo` |
| Nghĩ `compareTo` chỉ trả `-1/0/1` | Kiểm tra `<0`/`==0`/`>0` hoặc dùng `Integer.signum` |
| Cho rằng `17-ea` bằng `17` do cùng FEATURE | PRE đứng trước GA; so sánh đầy đủ |
| Cho rằng PRE numeric `10` nhỏ hơn `2` do chữ cái | PRE toàn chữ số so sánh numerically |
| Nghĩ `+BUILD` không tham gia thứ tự như SemVer | BUILD được so sánh, sau VNUM và PRE |
| Nghĩ `compareToIgnoreOptional` bỏ cả BUILD | Chỉ bỏ OPT, vẫn so sánh BUILD |
| Nghĩ `17.0` hoặc `17.0.0` là định dạng hợp lệ | Không. VNUM không cho zero cuối |
| Parse `1.8.0_202` như Java10+ VSTR | Cần adapter hoặc parser riêng cho legacy version |
| Dùng `major()/minor()/security()` cho code mới | Dùng `feature()/interim()/update()/patch()` |
| Để `TreeSet` bỏ OPT mà không nhận ra số lượng giảm | Chọn comparator/key theo policy rõ ràng |
| Dùng `equalsIgnoreOptional` nhưng trông chờ `HashSet` cũng bỏ OPT | Hash-based collection dùng `equals/hashCode` đầy đủ |
| Coi `LTS` trong OPT là bảo đảm hỗ trợ thực tế | Xác minh vendor/support policy ngoài chuỗi |
| Dùng `feature() >= 17` rồi cho rằng đó nhất định là GA | Cần xem `pre()` nếu yêu cầu không cho EA |
| Coi số BUILD lớn hơn là patch bảo mật mới hơn | So đúng VNUM trước, bảo mật cần dữ liệu riêng |
| Dùng `Runtime.Version` cho SemVer bất kỳ | Chọn parser/comparator đúng version scheme |
| Dùng `==` với Runtime.Version | Value-based class; dùng `equals` hoặc comparator |
| Gọi `Runtime.version()` và kỳ vọng phụ thuộc `javac --release` | Nó là version của JVM **đang chạy**, không phải target biên dịch |

## 18. Checklist code review

- [ ] Dữ liệu thực sự là chuỗi phiên bản JDK/Java SE theo JEP 322?
- [ ] Có dùng `Runtime.Version.parse` thay vì so sánh String thuần?
- [ ] Có xử lý `IllegalArgumentException` cho input sai format?
- [ ] Có kiểm tra null nếu dữ liệu đến từ cấu hình/HTTP?
- [ ] Đã phân biệt FEATURE, INTERIM, UPDATE, PATCH và các phần build?
- [ ] Đã tránh accessor deprecated `major/minor/security`?
- [ ] Có hiểu `PRE` đứng trước bản không PRE?
- [ ] Có dùng numeric ordering cho dãy số và numeric PRE?
- [ ] BUILD được so sánh sau PRE chứ không bị bỏ qua?
- [ ] Nếu dùng `compareToIgnoreOptional`, đã ghi rõ chỉ bỏ phần OPT?
- [ ] Nếu làm key trong `TreeSet`/`TreeMap`, comparator có làm các bản khác vendor trở thành trùng?
- [ ] Có khớp chính sách equality với comparator đã chọn?
- [ ] Nếu cần kiểm tra ngưỡng FEATURE, có phù hợp hơn khi dùng `feature()`?
- [ ] Có kiểm tra early-access khi policy yêu cầu GA?
- [ ] Có phân biệt bản runtime thực tế với build target và phiên bản đã parse từ file?
- [ ] Có dựa nhầm vào nhãn `LTS` để khẳng định support/security?
- [ ] Các test có bao gồm trailing zero, pre-release, build, optional và thứ tự numeric?

Gợi ý review có cơ sở:

> “Logic đang so sánh `String`, nên `17.0.10` có thể bị xếp thấp hơn `17.0.2`. Hãy dùng `Runtime.Version.parse` và `compareTo`; nếu muốn không tính nhãn vendor trong OPT thì dùng `compareToIgnoreOptional` có chủ đích.”

Một nhận xét khác:

> “`compareToIgnoreOptional` được dùng trong `TreeSet`, nên hai JDK chỉ khác `-LTS`/`-Vendor` sẽ bị coi là cùng key. Nếu cần theo dõi cả hai build, nên giữ comparator đầy đủ hoặc bổ sung key vendor.”

Không nên đề xuất:

> “Cứ cắt chuỗi tại dấu cộng rồi so sánh lexicographically cho đơn giản.”

Cách đó bỏ BUILD, dễ hiểu nhầm PRE và làm sai numeric ordering.

## 19. Bài tập có đáp án

**Câu 1.** `"17.0.10".compareTo("17.0.2")` và `Runtime.Version.compareTo` cho cùng hướng kết quả không?

**Đáp án:** Không. So sánh chuỗi có thể cho `17.0.10 < 17.0.2`, còn version ordering đúng là `17.0.10 > 17.0.2`.

**Câu 2.** `17-ea` hay `17` lớn hơn?

**Đáp án:** `17` lớn hơn vì bản không PRE đứng sau bản có PRE.

**Câu 3.** `17-2` hay `17-10` lớn hơn?

**Đáp án:** `17-10` lớn hơn vì PRE toàn chữ số so sánh theo số.

**Câu 4.** `17-10` hay `17-ea` lớn hơn?

**Đáp án:** `17-ea` lớn hơn vì PRE dạng số được coi nhỏ hơn PRE dạng không phải số.

**Câu 5.** `17` hay `17+1` lớn hơn theo `compareTo`?

**Đáp án:** `17+1` lớn hơn; bản có BUILD đứng sau bản không BUILD khi VNUM/PRE bằng nhau.

**Câu 6.** `17.0.1` hay `17+999` lớn hơn?

**Đáp án:** `17.0.1` lớn hơn. `VNUM` được so sánh trước BUILD.

**Câu 7.** `17+7-LTS` và `17+7-Vendor` có bằng nhau theo `compareToIgnoreOptional` không?

**Đáp án:** Có, kết quả bằng 0 vì chỉ khác OPT. Theo `compareTo` đầy đủ thì khác.

**Câu 8.** Nếu `17+7-LTS` và `17+8-LTS` khác BUILD, `compareToIgnoreOptional` có trả 0 không?

**Đáp án:** Không. Nó **vẫn** xét BUILD.

**Câu 9.** `Runtime.Version.parse("17.0")` hợp lệ không?

**Đáp án:** Không, vì version number không được có trailing zero element.

**Câu 10.** `Runtime.Version.parse("1.8.0_202")` có dùng được để so bản Java 8 theo chuẩn JDK 10 không?

**Đáp án:** Không. Đây là chuỗi kiểu cũ; cần adapter/version parser có hợp đồng riêng.

**Câu 11.** `Runtime.Version.parse("17.0.10+7-LTS").update()` trả gì?

**Đáp án:** `10`.

**Câu 12.** `Runtime.Version.parse("17.0.10+7-LTS").patch()` trả gì?

**Đáp án:** `0` vì PATCH vắng mặt.

**Câu 13.** Vì sao `TreeSet` dùng `Runtime.Version::compareToIgnoreOptional` có thể giảm số phần tử?

**Đáp án:** Vì comparator trả 0 cho các phiên bản chỉ khác OPT và `TreeSet` coi chúng là cùng một phần tử.

**Câu 14.** `equalsIgnoreOptional` có làm `HashSet` tự bỏ nhãn vendor không?

**Đáp án:** Không; `HashSet` dựa trên `equals/hashCode` mặc định của key.

**Câu 15.** `Runtime.version()` có phụ thuộc vào giá trị truyền cho `javac --release` lúc compile không?

**Đáp án:** Nó trả version của runtime đang chạy, không phải của build target.

**Câu 16.** Nếu muốn đảm bảo FEATURE ít nhất 17, dùng `current.feature() >= 17` có đủ để chắc chắn GA không?

**Đáp án:** Chưa. Nếu policy cấm early access, cần xem `pre()` hoặc chính sách so sánh với bản GA.

**Câu 17.** `LTS` trong OPT có chứng minh bản đó được vendor hỗ trợ trong một khoảng thời gian cụ thể không?

**Đáp án:** Không. Đây là metadata; cần kiểm tra thông tin hỗ trợ của vendor/distribution.

**Câu 18.** Có nên dùng `Runtime.Version` để so sánh `1.2.3-rc.1+meta` theo SemVer 2.0 không?

**Đáp án:** Không mặc định. Version scheme và comparator của Java JDK khác SemVer; dùng công cụ đúng scheme.

## 20. Tài liệu chính thức

- [Oracle JDK 10 — `Runtime.Version`](https://docs.oracle.com/javase/10/docs/api/java/lang/Runtime.Version.html): class, cú pháp phiên bản, toàn bộ thứ tự `compareTo`, `compareToIgnoreOptional`, equality và ý nghĩa các thành phần.
- [Oracle Java SE 21 — `Runtime.Version`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.Version.html): xác nhận các API và semantics còn áp dụng trong Java hiện đại.
- [OpenJDK JEP 223 — New Version-String Scheme](https://openjdk.org/jeps/223): cơ sở mô hình version strings được đưa vào từ Java 9.
- [OpenJDK JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322): mô hình FEATURE/INTERIM/UPDATE/PATCH của Java 10 và cách so sánh, naming accessors.
- [Oracle Java SE 21 — `Runtime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html): `Runtime.version()` lấy phiên bản Java Runtime đang chạy.
- [Oracle Java SE 21 — `Comparable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html): hợp đồng dấu của `compareTo` và tính nhất quán với equality.
- [Oracle Java SE 21 — `TreeSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html): tác động của comparator đến tính duy nhất của phần tử.
- [Semantic Versioning 2.0.0](https://semver.org/): chuẩn so sánh phiên bản sản phẩm cần phân biệt với JDK version scheme.

**Ghi nhớ:** `Runtime.Version.compareTo()` so sánh **VNUM → PRE → BUILD → OPT**, không so sánh chuỗi Java theo ký tự. `compareToIgnoreOptional()` **chỉ bỏ qua OPT**, không bỏ BUILD. Trong Java 10+, nên đọc `feature()/interim()/update()/patch()` thay cho accessor deprecated. Khi sử dụng sorted collections, ngưỡng tương thích hoặc metadata vendor, hãy chọn rõ chính sách so sánh và viết test cho các trường hợp biên; **version ordering không tự xác nhận bảo mật, hỗ trợ LTS hay tương thích thực tế**.