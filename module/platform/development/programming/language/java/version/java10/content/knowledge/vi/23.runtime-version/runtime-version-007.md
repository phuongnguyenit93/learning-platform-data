# `Runtime.Version.compareToIgnoreOptional()` và phần thông tin tùy chọn của phiên bản Java

## Mục tiêu

`java.lang.Runtime.Version` biểu diễn **version string của nền tảng Java** bằng các thành phần có cấu trúc. Khi cần so sánh hai phiên bản, lớp này cung cấp:

- `compareTo(Runtime.Version)`: so sánh **đầy đủ**, kể cả thông tin bổ sung ở cuối.
- `compareToIgnoreOptional(Runtime.Version)`: so sánh theo cùng quy tắc nhưng **bỏ qua riêng thành phần `OPT`** — optional build information.

Từ **Java 10**, sơ đồ số phiên bản Java tuân theo mô hình phát hành theo thời gian `FEATURE.INTERIM.UPDATE.PATCH` (JEP 322), vẫn được dùng trong Java hiện đại. Bản thân lớp `Runtime.Version` đã xuất hiện từ Java 9; không nên nói phương thức `compareToIgnoreOptional` là một tính năng chỉ tồn tại ở Java 10 hoặc đã bị loại bỏ.

Sau bài này, bạn sẽ:

1. Tách `VNUM`, `PRE`, `BUILD`, `OPT` trong một version string hợp lệ.
2. Phân biệt `build(): Optional<Integer>` và `optional(): Optional<String>`.
3. Biết chính xác `compareToIgnoreOptional` **vẫn xét** version numbers, pre-release và build number.
4. Dùng `equalsIgnoreOptional` đúng với chính sách so sánh và không nhầm với `equals`/`hashCode`.
5. Dự đoán tác động khi sắp xếp `TreeSet`, `TreeMap`, kiểm tra ngưỡng tối thiểu và nhận diện build.
6. Kiểm tra bằng Java 17+ với code có thể biên dịch và stdout đã được xác minh.

## 1. Cấu trúc version string trong Java 10+

Theo Javadoc `Runtime.Version`, chuỗi phiên bản gồm một dãy số phiên bản `VNUM`, có thể kèm thông tin phát hành sớm `PRE`, số build `BUILD` và thông tin bổ sung `OPT`. Ba dạng khái quát:

~~~text
VNUM(-PRE)?+BUILD(-OPT)?
VNUM-PRE(-OPT)?
VNUM+-OPT
~~~

Ký hiệu trong ba dòng trên chỉ diễn đạt cấu trúc, không phải biểu thức chính quy đầy đủ. Các dấu `+` và `-` trong chuỗi thực là **dấu phân cách**, còn dấu `?` ở mô tả thể hiện phần trước đó có thể vắng mặt.

| Phần | Chức năng | Ví dụ | API đọc |
| --- | --- | --- | --- |
| `VNUM` | Những số phiên bản ngăn bằng dấu chấm | `17.0.8` | `version()`, `feature()`, `interim()`, `update()`, `patch()` |
| `PRE` | Thông tin pre-release | `ea`, `internal` | `pre()` |
| `BUILD` | Số build | `7`, `12` | `build()` |
| `OPT` | Thông tin build bổ sung | `LTS`, `acme`, `zeta` | `optional()` |

Một số ví dụ **tự tạo để học API**, không khẳng định đã có bản JDK phát hành thật mang các nhãn này:

~~~text
17                    chỉ có VNUM
17.0.8                VNUM có UPDATE
17-ea                 VNUM + PRE
17+7                  VNUM + BUILD
17.0.8+7-acme         VNUM + BUILD + OPT
17.0.8-ea+7-acme      VNUM + PRE + BUILD + OPT
17+-note              VNUM + OPT, không có BUILD
17-ea-internal        VNUM + PRE + OPT, không có BUILD
~~~

**Điểm then chốt:** `BUILD` và `OPT` **không phải cùng một trường**. Khi gọi `compareToIgnoreOptional`, Java bỏ qua phần `OPT`, **không** bỏ qua toàn bộ `+BUILD`.

### Bốn thành phần số của Java 10

~~~java
Runtime.Version v = Runtime.Version.parse("17.0.8+7-acme");

System.out.println(v.version()); // [17, 0, 8]
System.out.println(v.feature()); // 17
System.out.println(v.interim()); // 0
System.out.println(v.update());  // 8
System.out.println(v.patch());   // 0
~~~

- `feature`: thế hệ phát hành tính năng.
- `interim`: chỉ số phát hành trung gian.
- `update`: chỉ số bản cập nhật.
- `patch`: chỉ số bản sửa khẩn cấp.

`version()` trả một `List<Integer>` không cho sửa, gồm những phần số **thực có trong VNUM**. Nó không tự bổ sung số 0 vào đuôi. Vì vậy `version()` ở ví dụ là `[17,0,8]`, mặc dù `patch()` trả 0.

Các accessor tên cũ `major()`, `minor()` và `security()` đã **deprecated** từ khi Java 10 làm rõ sơ đồ phiên bản. Trong code mới, sử dụng `feature()`, `interim()`, `update()`, `patch()`.

## 2. `optional()` khác `build()` và `pre()`

Ba accessor quan trọng có kiểu:

~~~java
Optional<String> pre()
Optional<Integer> build()
Optional<String> optional()
~~~

Chúng đều trả `Optional` vì các thành phần tương ứng **có thể vắng mặt**. Nhưng ý nghĩa khác nhau:

~~~java
Runtime.Version tagged =
        Runtime.Version.parse("17.0.8+7-acme");

System.out.println(tagged.pre().isPresent());          // false
System.out.println(tagged.build().orElse(-1));          // 7
System.out.println(tagged.optional().orElse("(none)")); // acme
~~~

`build()` là **số nguyên** `7`; `optional()` là **chuỗi** `"acme"`. Khi không có phần bổ sung:

~~~java
Runtime.Version plain =
        Runtime.Version.parse("17.0.8+7");

System.out.println(plain.build().isPresent());    // true
System.out.println(plain.optional().isPresent()); // false
~~~

Không có `OPT` đồng nghĩa `optional()` trả `Optional.empty()`, không phải một nhãn rỗng mà Java tự điền. Tránh gọi `optional().get()` khi chưa kiểm tra vì nếu vắng mặt sẽ ném `NoSuchElementException`. Dùng `orElse`, `ifPresent`, `map` hoặc cách xử lý `Optional` phù hợp.

### OPT vẫn có thể tồn tại khi không có BUILD

~~~java
Runtime.Version v = Runtime.Version.parse("17+-note");

System.out.println(v.build().isPresent());       // false
System.out.println(v.optional().orElse("none"));  // note
~~~

Vì có dạng `VNUM+-OPT`, đừng suy luận “không có số build thì chắc chắn không có optional info”.

Với dạng có PRE và OPT:

~~~java
Runtime.Version v = Runtime.Version.parse("17-ea-internal");

System.out.println(v.pre().orElse("none"));      // ea
System.out.println(v.build().isPresent());       // false
System.out.println(v.optional().orElse("none")); // internal
~~~

Đây là lý do code tự phân tách phiên bản bằng dấu `-` rất dễ nhầm **pre-release** với **optional build information**.

## 3. `compareTo()`: quy tắc đầy đủ

Chữ ký:

~~~java
public int compareTo(Runtime.Version other)
~~~

Javadoc quy định thứ tự ưu tiên so sánh:

1. **Dãy `VNUM`** — từng phần số được so theo giá trị **số học**.
2. **`PRE`** — khi VNUM bằng nhau, có nhãn pre-release được xếp **nhỏ hơn** bản không có pre-release.
3. **`BUILD`** — khi hai phần trước bằng nhau, build được so theo số; không có build **nhỏ hơn** có build.
4. **`OPT`** — sau cùng mới so lexicographic; nếu chỉ một bên có optional, bên **không có** được xếp nhỏ hơn.

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+7-zeta");

System.out.println(Integer.signum(a.compareTo(b))); // -1
~~~

VNUM, PRE, BUILD bằng nhau; `"acme"` đứng trước `"zeta"`, nên a nhỏ hơn b theo phép so sánh **đầy đủ**.

**Đừng kiểm tra `compareTo(...) == -1` hoặc `== 1` như một cam kết chung.** Kiểu trả về `int` chỉ cam kết **số âm, 0, số dương**. `Integer.signum` biến kết quả thành `-1/0/1` để tiện in hoặc test.

### Một bên thiếu `OPT`

~~~java
var plain = Runtime.Version.parse("17.0.8+7");
var tagged = Runtime.Version.parse("17.0.8+7-acme");

System.out.println(Integer.signum(plain.compareTo(tagged))); // -1
~~~

Kết quả nhỏ hơn là **thứ tự cú pháp** theo version-string contract, không phải chứng nhận chất lượng, bản vá hay mức bảo mật của build.

### Build number khác nhau

~~~java
var build7 = Runtime.Version.parse("17.0.8+7-acme");
var build8 = Runtime.Version.parse("17.0.8+8-zeta");

System.out.println(Integer.signum(build7.compareTo(build8))); // -1
~~~

Số `7` nhỏ hơn `8`; optional suffix không lấn át được thứ tự của build.

### Pre-release so với bản chính thức

~~~java
var early = Runtime.Version.parse("17.0.8-ea+7-acme");
var release = Runtime.Version.parse("17.0.8+7-acme");

System.out.println(Integer.signum(early.compareTo(release))); // -1
~~~

Một bản có PRE được xếp thấp hơn bản không có PRE, nếu VNUM tương ứng bằng nhau. Trong so sánh các nhãn PRE, chuỗi chỉ gồm số được so theo giá trị số; chuỗi không thuần số được so lexicographic và có thứ tự tương ứng theo hợp đồng Javadoc.

## 4. `compareToIgnoreOptional()`: bỏ qua **duy nhất OPT**

Chữ ký:

~~~java
public int compareToIgnoreOptional(Runtime.Version other)
~~~

Phương thức thực hiện phép so sánh tương tự `compareTo()` **nhưng không xét phần `OPT`**, kể cả khi một bên có optional còn bên kia không.

Nó **vẫn xét**:

- Các phần số phiên bản `VNUM`.
- Tính hiện diện/nội dung của nhãn pre-release `PRE`.
- Tính hiện diện/giá trị số của `BUILD`.

### Khi chỉ optional khác nhau

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+7-zeta");

System.out.println(Integer.signum(a.compareTo(b)));               // -1
System.out.println(Integer.signum(a.compareToIgnoreOptional(b))); // 0
~~~

`compareTo` phân biệt hai nhãn. `compareToIgnoreOptional` thấy VNUM/PRE/BUILD như nhau nên trả 0.

### Khi một phiên bản không có OPT

~~~java
var plain = Runtime.Version.parse("17.0.8+7");
var tagged = Runtime.Version.parse("17.0.8+7-acme");

System.out.println(plain.compareToIgnoreOptional(tagged)); // 0
~~~

Không có `OPT` hoặc có `OPT` khác nhau **không làm thay đổi** kết quả khi chỉ khác ở phần này.

### Khi BUILD khác nhau — vẫn phải phân biệt

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+8-zeta");

System.out.println(Integer.signum(a.compareToIgnoreOptional(b))); // -1
~~~

Đây là **phản ví dụ quan trọng nhất**: phương thức có chữ `IgnoreOptional` **không có nghĩa bỏ qua số build**. Nó vẫn kết luận build 7 nhỏ hơn build 8.

### Khi PRE khác nhau — vẫn phải phân biệt

~~~java
var early = Runtime.Version.parse("17.0.8-ea+7-acme");
var release = Runtime.Version.parse("17.0.8+7-zeta");

System.out.println(Integer.signum(
        early.compareToIgnoreOptional(release)
)); // -1
~~~

Vì bản early-access có `PRE`, nó thấp hơn bản release. Bỏ `OPT` không có nghĩa bỏ nhãn pre-release.

### Khi có OPT nhưng không có BUILD

~~~java
var optionalOnly = Runtime.Version.parse("17+-note");
var plain = Runtime.Version.parse("17");

System.out.println(Integer.signum(optionalOnly.compareTo(plain))); // 1
System.out.println(optionalOnly.compareToIgnoreOptional(plain));   // 0
~~~

Cả hai không có PRE/BUILD; sự khác nhau chỉ ở optional `note`. Phép so sánh đầy đủ phân biệt chúng, còn phép bỏ optional thì không.

## 5. Bảng so sánh những tình huống biên

Ký hiệu `<`, `=`, `>` là dấu của kết quả, không phải số `int` cụ thể.

| A | B | `compareTo` | `compareToIgnoreOptional` | Lý do |
| --- | --- | --- | --- | --- |
| `17.0.8+7-acme` | `17.0.8+7-zeta` | `<` | `=` | Chỉ `OPT` khác |
| `17.0.8+7` | `17.0.8+7-acme` | `<` | `=` | Một bên thiếu `OPT` |
| `17+-note` | `17` | `>` | `=` | Có `OPT`, đều không có `BUILD` |
| `17.0.8+7-acme` | `17.0.8+8-zeta` | `<` | `<` | Khác số `BUILD` |
| `17.0.8-ea+7-x` | `17.0.8+7-y` | `<` | `<` | Có PRE so với không PRE |
| `17.0.8+7-x` | `17.0.9+1-y` | `<` | `<` | Khác VNUM |
| `17+7-x` | `21+1-y` | `<` | `<` | Khác FEATURE |
| `17+7-x` | `17+7-x` | `=` | `=` | Giống toàn bộ |

Đọc bảng theo nguyên tắc: **chỉ khi các thành phần quan trọng trước OPT tương đương, tùy chọn bỏ OPT mới có thể làm kết quả từ khác nhau thành bằng 0**. Nếu đã có chênh lệch VNUM, PRE hoặc BUILD, cả hai phương thức vẫn ra cùng chiều thứ tự.

## 6. `equalsIgnoreOptional()` khác `equals()` thế nào?

`Runtime.Version` có hai phép kiểm tra bằng nhau tương ứng:

~~~java
boolean equals(Object other)
boolean equalsIgnoreOptional(Object other)
~~~

- `equals()`: hai đối tượng biểu diễn **cùng toàn bộ version string**.
- `equalsIgnoreOptional()`: hai phiên bản bằng nhau **nếu bỏ qua riêng OPT**.

~~~java
var acme = Runtime.Version.parse("17.0.8+7-acme");
var zeta = Runtime.Version.parse("17.0.8+7-zeta");

System.out.println(acme.equals(zeta));               // false
System.out.println(acme.equalsIgnoreOptional(zeta)); // true
~~~

Javadoc nêu tính nhất quán:

~~~text
a.compareTo(b) == 0
    phù hợp với
a.equals(b) == true

a.compareToIgnoreOptional(b) == 0
    phù hợp với
a.equalsIgnoreOptional(b) == true
~~~

Vì vậy **chọn một chính sách nhất quán**:

| Mục đích | So sánh thứ tự | Kiểm tra bằng nhau |
| --- | --- | --- |
| Nhận diện/sắp xếp toàn bộ version string | `compareTo` | `equals` |
| So sánh tương đương khi không quan tâm nhãn `OPT` | `compareToIgnoreOptional` | `equalsIgnoreOptional` |

Không suy ra `a.equals(b)` đúng chỉ vì `a.compareToIgnoreOptional(b) == 0`. Đây là **hai khái niệm tương đương khác nhau**, cùng tồn tại để phục vụ yêu cầu khác nhau.

## 7. `hashCode()` và collections: một cái bẫy dễ bỏ sót

`Runtime.Version.hashCode()` gắn với **`equals()` đầy đủ**. Không có một `hashCodeIgnoreOptional()` của Java dùng riêng với `equalsIgnoreOptional()`.

### `HashSet` và `HashMap` giữ hai build khác OPT

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+7-zeta");

Set<Runtime.Version> set = new HashSet<>(List.of(a, b));

System.out.println(set.size()); // 2
~~~

Mặc dù `a.equalsIgnoreOptional(b)` là true, `HashSet` vẫn dựa trên `equals()`/`hashCode()` thông thường nên không tự gộp chúng. `HashMap<Runtime.Version, V>` cũng phân biệt hai key này.

Nếu bạn muốn nhóm nhiều bản theo **phiên bản logic bỏ OPT**, cần tạo khóa logic hoặc cấu trúc nhóm theo chính sách nghiệp vụ. Không cố giả định bộ sưu tập hash sẽ hiểu một phương thức `equalsIgnoreOptional` riêng.

### `TreeSet` dùng comparator bỏ OPT có thể làm mất nhãn

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+7-zeta");

var full = new TreeSet<Runtime.Version>();
full.add(a);
full.add(b);

var ignoring = new TreeSet<Runtime.Version>(
        Runtime.Version::compareToIgnoreOptional
);
ignoring.add(a);
ignoring.add(b);

System.out.println(full.size());     // 2
System.out.println(ignoring.size()); // 1
~~~

`TreeSet` xác định phần tử trùng theo **kết quả của comparator**. Khi comparator trả 0, nó giữ lại một phần tử ngay cả khi `equals()` giữa chúng là false.

Những rủi ro:

1. Mất một nhãn tùy chọn mà log/audit/build inventory cần giữ.
2. Comparator bỏ `OPT` **không nhất quán với `equals()` đầy đủ** trong các trường hợp khác nhãn. Javadoc `TreeSet`/`SortedSet` cảnh báo comparator không nhất quán với equals có thể không tuân thủ đầy đủ hợp đồng `Set`.
3. `TreeMap` dùng cùng comparator cũng có thể coi hai key khác `OPT` là **cùng khóa**, ghi đè hoặc thay thế giá trị.

Nếu mục tiêu là bảo toàn từng artifact, hãy dùng **natural ordering `compareTo()`** hoặc một key đầy đủ. Chỉ dùng comparator bỏ optional khi việc **cố ý gộp** các phiên bản khác `OPT` đã được xác định, kiểm thử và ghi rõ.

## 8. Chương trình Java 17+ hoàn chỉnh, có stdout xác định

Lưu code vào tệp **VersionOptionalKnowledgeDemo.java**:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class VersionOptionalKnowledgeDemo {
    private static void compare(
            String label, Runtime.Version a, Runtime.Version b) {

        System.out.println(label + " full sign: "
                + Integer.signum(a.compareTo(b)));
        System.out.println(label + " ignore sign: "
                + Integer.signum(a.compareToIgnoreOptional(b)));
        System.out.println(label + " equals: "
                + a.equals(b));
        System.out.println(label + " equalsIgnore: "
                + a.equalsIgnoreOptional(b));
    }

    public static void main(String[] args) {
        Runtime.Version acme =
                Runtime.Version.parse("17.0.8+7-acme");
        Runtime.Version zeta =
                Runtime.Version.parse("17.0.8+7-zeta");
        Runtime.Version noOpt =
                Runtime.Version.parse("17.0.8+7");

        System.out.println("version parts: " + acme.version());
        System.out.println("feature/interim/update/patch: "
                + acme.feature() + "/" + acme.interim() + "/"
                + acme.update() + "/" + acme.patch());
        System.out.println("pre: "
                + acme.pre().orElse("(none)"));
        System.out.println("build: "
                + acme.build().orElse(-1));
        System.out.println("optional: "
                + acme.optional().orElse("(none)"));
        System.out.println("plain optional present: "
                + noOpt.optional().isPresent());

        compare("different opt", acme, zeta);
        compare("missing opt", noOpt, acme);
        compare(
                "different build",
                acme,
                Runtime.Version.parse("17.0.8+8-zeta")
        );
        compare(
                "ea vs release",
                Runtime.Version.parse("17.0.8-ea+7-acme"),
                acme
        );
        compare(
                "optional no build",
                Runtime.Version.parse("17+-note"),
                Runtime.Version.parse("17")
        );

        var full = new TreeSet<Runtime.Version>();
        full.add(acme);
        full.add(zeta);

        var ignoring = new TreeSet<Runtime.Version>(
                Runtime.Version::compareToIgnoreOptional
        );
        ignoring.add(acme);
        ignoring.add(zeta);

        System.out.println("full TreeSet size: " + full.size());
        System.out.println("ignore TreeSet size: " + ignoring.size());
        System.out.println("HashSet size: "
                + new HashSet<>(List.of(acme, zeta)).size());

        System.out.println("Java 17+ supported: "
                + (Runtime.version().feature() >= 17));

        try {
            Runtime.Version.parse("17.0");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid trailing zero: IllegalArgumentException"
            );
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VersionOptionalKnowledgeDemo.java
java VersionOptionalKnowledgeDemo
~~~

Kết quả **đã kiểm chứng trên JDK**, không phụ thuộc nhãn vendor/JVM hiện tại vì các cặp version đều là fixture:

~~~text
version parts: [17, 0, 8]
feature/interim/update/patch: 17/0/8/0
pre: (none)
build: 7
optional: acme
plain optional present: false
different opt full sign: -1
different opt ignore sign: 0
different opt equals: false
different opt equalsIgnore: true
missing opt full sign: -1
missing opt ignore sign: 0
missing opt equals: false
missing opt equalsIgnore: true
different build full sign: -1
different build ignore sign: -1
different build equals: false
different build equalsIgnore: false
ea vs release full sign: -1
ea vs release ignore sign: -1
ea vs release equals: false
ea vs release equalsIgnore: false
optional no build full sign: 1
optional no build ignore sign: 0
optional no build equals: false
optional no build equalsIgnore: true
full TreeSet size: 2
ignore TreeSet size: 1
HashSet size: 2
Java 17+ supported: true
invalid trailing zero: IllegalArgumentException
~~~

**Giải thích đầu ra:**

1. VNUM thực có ba phần, patch accessor trả 0. `build=7`, `optional=acme` cho thấy chúng khác nhau.
2. `different opt`/ `missing opt`: so đầy đủ khác nhau, bỏ OPT thì so bằng 0; `equalsIgnoreOptional` trả true.
3. `different build`: dù OPT bị bỏ qua, BUILD=7 vẫn nhỏ hơn BUILD=8.
4. `ea vs release`: PRE=ea thấp hơn bản không có PRE; hai phép so sánh cùng ra số âm.
5. `optional no build`: `17+-note` và `17` đều không có build, nhưng khác nhãn. Bỏ nhãn thì bằng 0.
6. `TreeSet` tự nhiên giữ hai chuỗi khác nhau, comparator bỏ OPT gộp còn một, `HashSet` vẫn giữ cả hai.
7. `Runtime.version().feature() >= 17` luôn true khi thực thi trên JDK 17+, không in bản runtime cụ thể.
8. `17.0` là version number không hợp lệ vì kết thúc bằng 0, parser ném `IllegalArgumentException`.

## 9. Những quy tắc sắp xếp khác cần biết

### Version numbers được so số học

~~~java
var eight = Runtime.Version.parse("17.0.8");
var ten = Runtime.Version.parse("17.0.10");

System.out.println(eight.compareToIgnoreOptional(ten) < 0);
// true
~~~

`8 < 10` theo **giá trị số**. So chuỗi `String.compareTo` có thể kết luận sai, nên không dùng cách so sánh text để quyết định phiên bản Java.

Nếu hai dãy số khác độ dài, thành phần tồn tại ở bên dài được so theo quy tắc Javadoc; `17.0.8` và `17.0.8.1` không tương đương. Phần `OPT` không thể làm đảo thứ tự của VNUM.

### Pre-release khác release

- Với VNUM bằng nhau, có PRE luôn thấp hơn không có PRE.
- PRE chỉ chứa chữ số được so theo số.
- PRE có chữ được so lexicographic.
- Nhãn PRE dạng số nhỏ hơn dạng không thuần số khi đến bước so PRE.

Không tự tìm từ `"ea"` ở một vị trí bất kỳ trong chuỗi: chỉ `pre()` cho biết phần đó thật sự là pre-release.

### Build number vẫn có ý nghĩa

Không có BUILD được xếp nhỏ hơn có BUILD nếu các thành phần trước bằng nhau. Khi cả hai có BUILD, số được so **số học**. Vì vậy `17+7-zeta` nhỏ hơn `17+12-acme` theo cả hai cách so sánh, dù nhãn `zeta` đứng sau `acme` trong thứ tự từ điển.

### Optional không đánh giá được mức hỗ trợ

Theo JEP 322, một nhãn `OPT` bắt đầu bằng `LTS` có thể dùng để thể hiện dòng được nhà triển khai hỗ trợ dài hạn. Tuy nhiên:

- Đây không phải cam kết **đang được hỗ trợ** ở thời điểm thực thi.
- Nhãn `LTS` không thay thế kiểm tra nhà phát hành, hạn hỗ trợ, advisory bảo mật hoặc quyền sử dụng.
- Hai build có cùng VNUM/BUILD nhưng khác optional có thể khác binary artifact thực tế, checksum, provenance hoặc chính sách đóng gói.

`compareToIgnoreOptional` là **chính sách thứ tự**, không phải phép xác minh tương đương mã nhị phân hay bảo mật.

## 10. Dùng trong ứng dụng: khi nào bỏ optional, khi nào không?

| Tình huống | Cách cân nhắc | Lý do |
| --- | --- | --- |
| Kiểm tra JVM có Java feature 17+ | `Runtime.version().feature() >= 17` | Không cần so nhãn `OPT` |
| So version string đầy đủ để ghi inventory | `compareTo()`, `equals()`, `toString()` | Không làm mất thông tin |
| So mốc cập nhật mà policy không quan tâm `OPT` | `compareToIgnoreOptional()` | Vẫn xét VNUM/PRE/BUILD |
| Kiểm tra cùng mốc version bỏ nhãn | `equalsIgnoreOptional()` | Nhất quán với comparator |
| Xác định một artifact hoặc build vendor cụ thể | Giữ `OPT` và metadata provenance | Không gộp các bản khác nhau |
| Sắp xếp đầy đủ phiên bản trong `TreeSet` | Natural order `compareTo()` | Tránh mất phần tử |
| Dùng `TreeSet` làm tập các mốc bỏ OPT | Comparator bỏ OPT, **nếu cố ý** | Phải chấp nhận việc gộp và cảnh báo không nhất quán với equals |
| Key trong `HashMap` | `equals/hashCode` đầy đủ | HashMap không có policy bỏ OPT |
| So version Maven, SemVer hoặc thư viện riêng | Parser/policy của hệ phiên bản đó | `Runtime.Version` không giải mọi phiên bản |

### Chỉ cần kiểm tra Java feature hiện tại

~~~java
int feature = Runtime.version().feature();

if (feature >= 17) {
    // JVM có feature version ít nhất 17.
}
~~~

Đây là đoạn mã **trong một phương thức**. Đừng dựa vào `System.getProperty("java.version").compareTo("17")`; đó là so chuỗi, không phải so phiên bản cấu trúc.

### Khi cần một ngưỡng bản update/build cụ thể

~~~java
Runtime.Version minimum =
        Runtime.Version.parse("17.0.8+7");

Runtime.Version actual =
        Runtime.version();

boolean meetsThreshold =
        actual.compareToIgnoreOptional(minimum) >= 0;
~~~

Đoạn trên minh họa phép so sánh; nó không bảo đảm **tương thích tính năng, bản vá bảo mật hay tương đương nhà phân phối**. Nếu policy cần cả PRE/BUILD, so sánh trên là phù hợp về mặt version ordering; nếu policy cần kiểm tra nhãn `OPT` hay vendor, hãy thiết kế thêm kiểm tra riêng thay vì bỏ qua.

Một bản đã được backport patch bảo mật có thể không có số version so sánh như một bản vendor khác. Không quyết định an toàn của runtime chỉ bằng phép so version.

## 11. `Runtime.version()` không giống `Runtime.Version.parse(...)`

~~~java
Runtime.Version running = Runtime.version();

Runtime.Version fixture =
        Runtime.Version.parse("17.0.8+7-acme");
~~~

- `Runtime.version()` phản ánh **bản Java runtime đang chạy**.
- `Runtime.Version.parse(String)` tạo một phiên bản theo **chuỗi cung cấp**, không cần phiên bản ấy thực sự tồn tại hoặc đã được cài trên máy.

Trong unit test, nên dùng các fixture tường minh để tránh test thay đổi khi CI đổi từ JDK 17 sang JDK 21 hoặc một JDK mới hơn.

~~~java
var a = Runtime.Version.parse("17.0.8+7-acme");
var b = Runtime.Version.parse("17.0.8+7-zeta");

boolean sameIgnoringOpt =
        a.compareToIgnoreOptional(b) == 0;

// sameIgnoringOpt luôn true trên Java tuân thủ API.
~~~

Không in `Runtime.version().toString()` rồi công bố một stdout cố định nếu không kiểm soát runtime. Chương trình hoàn chỉnh trong bài chỉ in một boolean luôn đúng với điều kiện chạy Java 17+.

## 12. Parse sai định dạng và xử lý ngoại lệ

Một version number hợp lệ có các quy tắc quan trọng:

- Thành phần số không được dùng leading zeros không hợp lệ.
- VNUM bắt đầu bằng số dương.
- Phần tử **cuối** của VNUM không được bằng 0.
- VNUM có thể dài hơn bốn phần số, dù bốn phần đầu có tên ngữ nghĩa chính.
- PRE/BUILD/OPT cần đúng vị trí và cú pháp như hợp đồng của `Runtime.Version.parse`.

Ví dụ:

~~~java
Runtime.Version.parse("17");           // hợp lệ
Runtime.Version.parse("17.0.8");       // hợp lệ
Runtime.Version.parse("17.0.8+7-LTS"); // hợp lệ

// Lỗi: VNUM kết thúc bằng 0.
// Runtime.Version.parse("17.0");

// Lỗi: 00 là phần số có leading zero.
// Runtime.Version.parse("17.00.8");
~~~

Với dữ liệu đến từ người dùng hoặc file cấu hình, `parse` có thể ném `IllegalArgumentException` khi chuỗi không đúng định dạng. `compareTo` và `compareToIgnoreOptional` ném `NullPointerException` nếu đối số khác version là `null`.

~~~java
static Runtime.Version parseRequiredVersion(String raw) {
    try {
        return Runtime.Version.parse(raw);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Version string không hợp lệ", ex
        );
    }
}
~~~

Đây là **phương thức minh họa trong class**, không phải chương trình độc lập. Trong môi trường có input không đáng tin, đừng đưa nguyên dữ liệu thô vào log hoặc thông báo lỗi công khai nếu nó chứa thông tin nhạy cảm.

### Không `split("-")` hoặc `split("+")` để giả lập IgnoreOptional

~~~java
// Sai về ý tưởng: lấy mọi thứ trước dấu '-' làm version.
// String simplified = text.split("-")[0];
~~~

Dấu `-` có thể mở đầu **PRE**, một thành phần phải **được giữ trong phép so sánh bỏ OPT**. Nó cũng có thể xuất hiện trong phần `OPT`. Dấu `+` có thể mở đầu BUILD hoặc chuỗi `+-OPT`. Do đó cách cắt chuỗi tùy ý không thể thay chính xác thuật toán của Java.

**Giải pháp:** parse version bằng `Runtime.Version.parse`, rồi gọi `compareToIgnoreOptional` trực tiếp.

## 13. Các tình huống cần kiểm thử

Một bộ kiểm thử tốt cần tách **từng thành phần**:

| Kiểm thử | Kỳ vọng `compareToIgnoreOptional` | Kỳ vọng `compareTo` |
| --- | --- | --- |
| Cùng VNUM/PRE/BUILD, OPT khác | 0 | Khác 0 |
| Cùng VNUM/PRE/BUILD, OPT vắng ở một phía | 0 | Khác 0 |
| BUILD 7 so với BUILD 8 | Khác 0 | Khác 0 |
| Có PRE so với không PRE | Khác 0 | Khác 0 |
| VNUM khác | Khác 0 | Khác 0 |
| Cùng tất cả thành phần | 0 | 0 |
| Có OPT nhưng không BUILD | Bỏ OPT | Vẫn xét OPT |
| Chuỗi sai `17.0` | Không parse thành công | `IllegalArgumentException` |
| So với `null` | `NullPointerException` | `NullPointerException` |

Nên kiểm tra cả **tính nhất quán với equalsIgnoreOptional**:

~~~java
Runtime.Version a =
        Runtime.Version.parse("17.0.8+7-acme");
Runtime.Version b =
        Runtime.Version.parse("17.0.8+7-zeta");

if ((a.compareToIgnoreOptional(b) == 0)
        != a.equalsIgnoreOptional(b)) {
    throw new AssertionError("Comparison inconsistent");
}
~~~

Các thuộc tính khác đáng kiểm tra nếu dùng comparator trong sorting:

1. Dấu so sánh đối xứng: `sign(compare(a,b)) == -sign(compare(b,a))`.
2. Tính bắc cầu của thứ tự.
3. Mọi trường hợp comparator trả 0 có được ứng dụng **cố ý** xem là tương đương?
4. Số phần tử còn lại trong `TreeSet` có đúng theo mục tiêu của bài toán?

Không lấy việc `equalsIgnoreOptional` true để khẳng định `hashCode` của hai Version phải bằng nhau: hợp đồng hashCode của object gắn với `equals` đầy đủ.

## 14. Lỗi thường gặp

| Hiểu nhầm | Sai ở đâu? | Sửa thế nào? |
| --- | --- | --- |
| “Ignore optional là bỏ toàn bộ build.” | BUILD khác OPT; số build vẫn được so. | Test cặp `+7` và `+8`. |
| “Khi không có BUILD thì không thể có OPT.” | Dạng `VNUM+-OPT` hợp lệ. | Dùng `optional()` và `build()` riêng. |
| “Bỏ optional cũng bỏ PRE.” | PRE là thành phần so sánh có thứ tự cao hơn. | Test `-ea` so với bản release. |
| “`compareToIgnoreOptional==0` suy ra `equals==true`.” | `equals` so toàn bộ OPT. | Dùng `equalsIgnoreOptional`. |
| “`HashSet` cũng gộp khi `equalsIgnoreOptional` true.” | HashSet dùng equals/hashCode thường. | Thiết kế key logic riêng. |
| “`TreeSet` comparator bỏ OPT vẫn giữ mọi bản.” | Comparator bằng 0 làm Set gộp. | Natural order khi cần artifact đầy đủ. |
| “`compareTo` luôn đúng -1 hoặc 1.” | Chỉ cam kết âm/0/dương. | Dùng `Integer.signum`. |
| “So `String` là đủ.” | Lexicographic có thể sai với số 8 và 10. | Parse thành `Runtime.Version`. |
| “Tách tại dấu `-` là đã bỏ OPT.” | Dấu `-` còn mở đầu PRE. | Dùng API chuẩn. |
| “`optional().get()` luôn có dữ liệu.” | `OPT` có thể vắng. | Dùng `orElse`/`ifPresent`. |
| “`optional()` là số build.” | `optional` là String; build là Integer. | Đọc đúng accessor. |
| “`LTS` trong OPT chứng minh đang được bảo mật.” | Đây là nhãn phụ; cần đối chiếu nhà phân phối. | Kiểm tra advisory/support riêng. |
| “Dùng `Runtime.Version` cho mọi phiên bản SemVer.” | Cú pháp/so sánh Java khác hệ phiên bản thư viện. | Dùng version policy phù hợp. |
| “`Runtime.Version.parse` kiểm tra bản JDK được cài.” | Nó chỉ parse chuỗi. | Dùng `Runtime.version()` khi cần. |
| “`major/minor/security` là tên nên dùng trong code mới.” | Các tên này deprecated theo JEP 322. | Dùng `feature/interim/update/patch`. |
| “So identity `==` là đủ.” | Runtime.Version là lớp value-based. | Dùng `equals` hoặc `equalsIgnoreOptional`. |

## 15. Bài tập tự kiểm tra

### Bài 1 — hai build chỉ khác nhãn

~~~java
var x = Runtime.Version.parse("21+12-LTS");
var y = Runtime.Version.parse("21+12-vendor");
~~~

Hãy xác định `x.compareToIgnoreOptional(y) == 0`, `x.equals(y)`, `x.equalsIgnoreOptional(y)`.

**Đáp án:** `true`, `false`, `true`. Hai bản cùng VNUM/BUILD, chỉ khác OPT.

### Bài 2 — BUILD quan trọng đến đâu?

~~~java
var x = Runtime.Version.parse("21+12-LTS");
var y = Runtime.Version.parse("21+13-vendor");
~~~

Hỏi `x.compareToIgnoreOptional(y)` có bằng 0 không?

**Đáp án:** Không. BUILD=12 nhỏ hơn BUILD=13 nên cho kết quả âm. Phương thức chỉ bỏ **OPT**.

### Bài 3 — PRE không bị bỏ

~~~java
var x = Runtime.Version.parse("21-ea+12-LTS");
var y = Runtime.Version.parse("21+12-vendor");
~~~

**Đáp án:** `x.compareToIgnoreOptional(y) < 0` vì bản có PRE được xếp trước bản không có PRE cùng VNUM.

### Bài 4 — Optional rỗng

~~~java
var v = Runtime.Version.parse("21+12");

System.out.println(v.optional().isPresent());
System.out.println(v.build().orElse(-1));
~~~

**Stdout:**

~~~text
false
12
~~~

### Bài 5 — `TreeSet` và `HashSet`

~~~java
var a = Runtime.Version.parse("17+7-first");
var b = Runtime.Version.parse("17+7-second");
~~~

Hỏi `HashSet` thường và `TreeSet` với comparator `Runtime.Version::compareToIgnoreOptional` có kích thước thế nào nếu thêm cả a và b?

**Đáp án:** `HashSet` có 2, `TreeSet` theo comparator bỏ OPT có 1. Nếu cần ghi nhận mọi artifact, lựa chọn TreeSet này không phù hợp.

### Bài 6 — kiểm tra feature

Ứng dụng yêu cầu Java feature 17 hoặc cao hơn. Cách nên dùng?

**Đáp án:** `Runtime.version().feature() >= 17`. Không so lexicographic chuỗi `java.version` và không cần quan tâm `OPT` nếu chỉ xét feature.

### Bài 7 — có OPT nhưng không có BUILD

~~~java
var v = Runtime.Version.parse("21+-note");
~~~

**Đáp án:** `v.optional().orElse("none")` trả `"note"`; `v.build().isPresent()` trả `false`. Hai trường độc lập về sự có mặt.

## 16. Tóm tắt và tài liệu chính thức

- `Runtime.Version` là API cho version string Java, từ Java 9 và vẫn hiện hành.
- Java 10 định nghĩa rõ `FEATURE.INTERIM.UPDATE.PATCH`; dùng `feature()`, `interim()`, `update()`, `patch()`, không dùng accessor deprecated.
- **`compareTo()` so VNUM → PRE → BUILD → OPT.**
- **`compareToIgnoreOptional()` vẫn so VNUM, PRE, BUILD; chỉ bỏ qua OPT.**
- `build()` trả `Optional<Integer>`, `optional()` trả `Optional<String>`; `OPT` có thể xuất hiện cả khi không có số BUILD.
- `compareToIgnoreOptional()==0` phù hợp với `equalsIgnoreOptional()`, **không** suy ra `equals()` đầy đủ đúng.
- `HashSet` dùng equals/hashCode đầy đủ; `TreeSet` với comparator bỏ optional có thể gộp các bản khác nhãn.
- `Runtime.version()` đọc runtime thực; `Runtime.Version.parse` tạo fixture từ chuỗi.
- Chỉ dùng phép so phiên bản để thực thi **chính sách version ordering**; không dùng thay xác minh binary provenance, mức hỗ trợ hay bản vá bảo mật.

Tài liệu chuẩn còn áp dụng:

- [Java SE 17 — `Runtime.Version`, `optional`, `compareToIgnoreOptional`, `equalsIgnoreOptional`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html)
- [Java SE 10 — `Runtime.Version`](https://docs.oracle.com/javase/10/docs/api/java/lang/Runtime.Version.html)
- [Java SE 17 — `Runtime.version()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#version())
- [Java SE 17 — `TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322)

**Kết luận:** Nếu bạn muốn hai bản Java **chỉ khác metadata `OPT`** được coi là tương đương, hãy dùng `compareToIgnoreOptional()` cùng `equalsIgnoreOptional()`. Nhưng đừng bỏ qua `PRE`, đừng quên `BUILD`, và đừng dùng thứ tự bỏ OPT để làm mất bản build riêng biệt mà hệ thống cần theo dõi.
