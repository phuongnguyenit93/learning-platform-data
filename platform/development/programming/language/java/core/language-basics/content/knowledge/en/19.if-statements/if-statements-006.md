# Điều kiện biên và thứ tự xét các nhánh — Java 17+

## 1. Mục tiêu

Trong Java, `if`, `else if` và `else` giúp chọn nhánh theo điều kiện `boolean`. Hai nguồn lỗi phổ biến là:

1. **Sai điều kiện biên** (*boundary condition*): viết `>` thay vì `>=`, bỏ sót điểm đầu/cuối, hoặc chấp nhận dữ liệu ngoài miền.
2. **Sai thứ tự nhánh**: một điều kiện rộng đứng trước đã nhận mất những giá trị lẽ ra phải thuộc nhánh cụ thể phía sau.

~~~java
int score = 90;
if (score >= 90) {
    System.out.println("A");
} else if (score >= 70) {
    System.out.println("B");
} else {
    System.out.println("C");
}
~~~

**Expected stdout:**

~~~text
A
~~~

Khi `score == 90`, nhánh `score >= 90` là true và chạy trước; các nhánh `else if` và `else` **không được đánh giá/thực hiện**.

Trong bài, ta học cách đặc tả miền, sắp điều kiện theo thứ tự rõ ràng, xác thực giá trị, tránh nhánh che khuất và xây dựng kiểm thử tại biên bằng Java 17+.

## 2. Thứ tự xét nhánh là một phần của điều kiện biên

Một chuỗi `if / else if / else` duyệt điều kiện **từ trên xuống** và dừng ở nhánh đúng đầu tiên. Điều đó khiến thứ tự nhánh và toán tử so sánh **phối hợp** quyết định khoảng giá trị mà mỗi nhánh thực sự nhận:

~~~java
if (score >= 90) {
    grade = "A";
} else if (score >= 70) {
    grade = "B"; // Chỉ nhận 70..89 khi score là int hợp lệ.
} else {
    grade = "C"; // Nhận dưới 70 trong miền hợp lệ.
}
~~~

Không phải mọi biểu thức được đánh giá: với `score=95`, điều kiện nhánh B không được xét. Nếu đảo điều kiện `>=70` lên trước, nhánh A có thể trở nên không thể chọn dù cú pháp vẫn hợp lệ.

Bài này tập trung **miền, điểm biên và nhánh bị che khuất**. Chi tiết về độc lập hay loại trừ khi có nhiều `if` đã thuộc bài trước; vì vậy khi review một chuỗi, hãy ưu tiên vẽ **khoảng thực tế** của từng nhánh thay vì chỉ đếm bao nhiêu nhánh chạy.


## 3. Biên đóng và mở: `<`, `<=`, `>`, `>=`

Trước khi viết code, hãy xác định **giá trị bằng đúng biên có được chấp nhận hay không**.

| Mô tả | Điều kiện Java | Giá trị đúng tại biên |
|---|---|---|
| Lớn hơn 18 | `age > 18` | 18 bị loại |
| Từ đủ 18 tuổi | `age >= 18` | 18 được nhận |
| Dưới 65 | `age < 65` | 65 bị loại |
| Tối đa 65 | `age <= 65` | 65 được nhận |
| Khoảng đóng 18 đến 65 | `age >= 18 && age <= 65` | Nhận 18 và 65 |
| Khoảng nửa mở 0 đến `length` | `index >= 0 && index < length` | Nhận 0, loại `length` |

Ví dụ:

~~~java
int age = 18;
boolean adult = age >= 18;
System.out.println(adult); // true
~~~

Java **không cho viết** `18 <= age <= 65`. Hãy dùng hai biểu thức boolean nối bằng `&&`:

~~~java
boolean eligible = age >= 18 && age <= 65;
~~~

Các giá trị nằm ngay ngoài miền cũng phải được kiểm tra; chúng thường phát hiện lỗi *off-by-one*.

## 4. Sắp nhánh theo thứ tự từ điều kiện cụ thể đến bao quát

Giả sử yêu cầu:

- Từ 65 tuổi: `SENIOR`.
- Từ 18 đến dưới 65: `ADULT`.
- Dưới 18: `MINOR`.

**Thứ tự sai:**

~~~java
if (age >= 18) {
    group = "ADULT";
} else if (age >= 65) {
    group = "SENIOR"; // Không bao giờ được chọn cho tuổi >= 65
} else {
    group = "MINOR";
}
~~~

Với `age = 70`, nhánh đầu đã đúng. Điều kiện `age >= 65` **bị che khuất về logic** mặc dù vẫn có cú pháp hợp lệ. Compiler không bắt buộc báo lỗi cho trường hợp này.

**Thứ tự đúng:**

~~~java
if (age >= 65) {
    group = "SENIOR";
} else if (age >= 18) {
    group = "ADULT";
} else {
    group = "MINOR";
}
~~~

Bởi vì khi tới nhánh thứ hai, `age >= 65` đã được loại, nên `age >= 18` ở đó ngầm chỉ khoảng `[18, 65)`.

Nếu chính sách phân loại có nhiều điều kiện giao nhau nhưng **ưu tiên khác nhau** (ví dụ trạng thái khẩn cấp phải thắng trạng thái thường), hãy ghi rõ mức ưu tiên đó trước rồi mới sắp nhánh, thay vì áp dụng một quy tắc sắp xếp máy móc.

## 5. Đặc tả miền cho hệ thống phân loại điểm

Giả sử `score` phải từ **0 đến 100** và có bốn mức:

| Điểm | Nhãn | Điều kiện |
|---|---|---|
| Ngoài `[0,100]` | `INVALID` | `score < 0 \|\| score > 100` |
| `[90,100]` | `A` | `score >= 90`, sau khi đã validate |
| `[70,90)` | `B` | `score >= 70`, sau khi A không đúng |
| `[50,70)` | `C` | `score >= 50`, sau khi A/B không đúng |
| `[0,50)` | `D` | `else` |

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    }
    if (score >= 90) {
        return "A";
    } else if (score >= 70) {
        return "B";
    } else if (score >= 50) {
        return "C";
    } else {
        return "D";
    }
}
~~~

**Đặc điểm đáng chú ý:**

- Kiểm tra miền hợp lệ **trước khi phân loại**, nên `score = 101` không bị nhận nhầm là A.
- Kiểm tra ngưỡng giảm dần `90 → 70 → 50`; ngưỡng lớn không bị nhánh rộng che khuất.
- `score = 90` là A, `score = 70` là B, `score = 50` là C.
- `score = 0` là D, `score = 100` là A.
- Không cần lặp lại `score < 90` trong nhánh B vì nhánh A đã thất bại.

Với dữ liệu ngoài miền, một hệ thống khác có thể **ném `IllegalArgumentException`** thay vì trả `INVALID`. Chọn theo hợp đồng API; không ngầm “clamp” về miền 0–100 nếu người dùng không yêu cầu.

## 6. Bảng test biên — mỗi ngưỡng nên thử ba điểm

Với điểm nguyên, tối thiểu thử ngay dưới, đúng bằng và ngay trên ngưỡng, cộng thêm biên toàn miền:

| `score` | Expected | Mục đích |
|---:|---|---|
| -1 | `INVALID` | Dưới miền |
| 0 | `D` | Biên dưới hợp lệ |
| 49 | `D` | Ngay dưới ngưỡng 50 |
| 50 | `C` | Đúng ngưỡng 50 |
| 51 | `C` | Ngay trên ngưỡng 50 |
| 69 | `C` | Ngay dưới ngưỡng 70 |
| 70 | `B` | Đúng ngưỡng 70 |
| 71 | `B` | Ngay trên ngưỡng 70 |
| 89 | `B` | Ngay dưới ngưỡng 90 |
| 90 | `A` | Đúng ngưỡng 90 |
| 91 | `A` | Ngay trên ngưỡng 90 |
| 100 | `A` | Biên trên hợp lệ |
| 101 | `INVALID` | Trên miền |

Điểm mấu chốt: chỉ thử một giá trị “giữa khoảng” như 75 là **chưa đủ** để phát hiện việc dùng sai `>`/`>=`.

Nếu kiểu dữ liệu là `long` và biên gần `Long.MIN_VALUE`/`Long.MAX_VALUE`, **không tính máy móc `min - 1` hoặc `max + 1`** vì có thể overflow. Hãy dùng các giá trị kiểm thử có biểu diễn hợp lệ trong kiểu.

## 7. Chú ý khi điều kiện giao nhau hoặc không phủ hết miền

Với hai điều kiện:

~~~java
if (value >= 10) {
    label = "TEN_OR_MORE";
} else if (value >= 20) {
    label = "TWENTY_OR_MORE"; // Bị che khuất
}
~~~

Nhánh thứ hai không nhận giá trị nào vì mọi số `>=20` đã thuộc nhánh đầu.

Ngược lại, nếu thiếu `else` hoặc một ngưỡng:

~~~java
String label = "UNKNOWN";
if (value < 0) {
    label = "NEGATIVE";
} else if (value > 0) {
    label = "POSITIVE";
}
// value == 0 => giữ UNKNOWN
~~~

Đây có thể là **chủ ý** nếu `UNKNOWN` là trạng thái hợp lệ, hoặc là bug nếu phải phân loại mọi số. Hãy lập bảng miền và xác định có cần bao phủ đầy đủ (*exhaustive*) không.

Đối với những điều kiện không phải ngưỡng đơn điệu (ví dụ `isAdmin`, `isSuspended`, `age >= 18`), hãy **đặt ưu tiên quy tắc rõ ràng**, thay vì mặc định xếp theo độ lớn.

## 8. Ngoặc nhọn giúp điều kiện biên thuộc đúng nhánh

Với `if` lồng nhau, một `else` không ngoặc có thể gắn với `if` gần nhất còn thiếu `else`, dù người đọc tưởng đó là nhánh ngoài. Điều này có thể làm **sai điều kiện kiểm tra biên** vì nhánh dự phòng thuộc một điều kiện khác:

~~~java
if (validRange) {
    if (score >= 90) {
        System.out.println("A");
    }
} else {
    System.out.println("INVALID");
}
~~~

Ở đây `else` thuộc `if (validRange)`, nên mọi điểm **ngoài miền** được đánh dấu INVALID. Nếu muốn báo mức thấp cho điểm hợp lệ, cần thêm một `else` **bên trong** khối `validRange` hoặc dùng chuỗi phân loại đã kiểm tra miền như `grade(int)` trong chương trình chính.

Không để sự nhập nhằng ngoặc nhọn làm đảo ý nghĩa bảng biên; quy tắc `dangling else` và các biến thể cú pháp được trình bày toàn diện trong bài riêng.


## 9. Thứ tự đánh giá có thể ảnh hưởng side effect và exception

~~~java
static boolean check(String name, boolean answer) {
    System.out.println("checked " + name);
    return answer;
}
~~~

~~~java
if (check("first", false)) {
    System.out.println("first branch");
} else if (check("second", true)) {
    System.out.println("second branch");
} else if (check("third", true)) {
    System.out.println("third branch");
}
~~~

**Expected stdout:**

~~~text
checked first
checked second
second branch
~~~

Nhánh `third` **không được kiểm tra** vì nhánh thứ hai đã true. Do đó, đổi thứ tự các nhánh không phải lúc nào cũng chỉ đổi nhãn kết quả: nó có thể đổi **method nào được gọi, side effect nào xảy ra hoặc exception nào xuất hiện**.

Khuyến nghị: các điều kiện phân loại thông thường nên **thuần túy, không cập nhật trạng thái**. Nếu cần log hoặc xác thực nhiều trường, tách thao tác thành bước rõ ràng.

### Guard với `&&` và `||`

~~~java
int[] numbers = {10, 20, 30};
int index = 2;

if (numbers != null
        && index >= 0
        && index < numbers.length) {
    System.out.println(numbers[index]); // 30
}
~~~

Guard ở vế trái đi trước thao tác có thể lỗi. `&&` dừng ngay khi gặp false. Nếu dùng `&` boolean hoặc đặt thao tác truy cập trước guard, có thể ném `NullPointerException` / `ArrayIndexOutOfBoundsException`.

## 10. Biên `double`: giá trị biểu diễn và chính sách sai số

Khi kiểm tra một ngưỡng số thực, `>=`, `<=` so **giá trị `double` đã được biểu diễn**, không tự áp dụng dung sai:

~~~java
double computed = 0.1 + 0.2;

System.out.println(computed);        // 0.30000000000000004
System.out.println(computed <= 0.3); // false
~~~

Nếu nghiệp vụ quy định giá trị chấp nhận sai số, hãy đặc tả ngưỡng dựa trên **đơn vị và yêu cầu**. Không tự nới một biên cứng chỉ để test thành công.

Đối với `NaN`, mọi phép so sánh thứ tự `<`, `<=`, `>`, `>=` đều false. Vì thế, nếu đầu vào buộc phải hữu hạn:

~~~java
static boolean isValidRatio(double ratio) {
    return Double.isFinite(ratio)
            && ratio >= 0.0
            && ratio <= 1.0;
}
~~~

**Không dùng** `if (ratio < 0 || ratio > 1)` làm kiểm tra duy nhất để từ chối dữ liệu không hợp lệ: `NaN` không thỏa vế nào và có thể lọt qua.

## 11. Viết code dễ đọc và dễ kiểm thử

Một số nguyên tắc:

1. **Đặt tên cho ngưỡng** khi có ý nghĩa nghiệp vụ: `PASS_MARK`, `SENIOR_AGE`, `FREE_SHIPPING_FROM`.
2. **Từ chối giá trị ngoài miền trước**, sau đó mới phân loại.
3. Nếu xét ngưỡng giảm/tăng dần, giữ thứ tự nhất quán và đảm bảo nhánh trước không che nhánh sau.
4. Nếu quy tắc **có ưu tiên**, đặt quy tắc ưu tiên cao hơn trước và ghi chú tại sao.
5. **Tránh thay đổi biến ngay trong điều kiện** như `if (index++ < length)` nếu nhánh sau còn dùng nó.
6. Dùng **ngoặc nhọn** và **bảng kiểm thử biên** để tránh lỗi off-by-one hoặc dangling else.
7. Test **kết quả** và, nếu điều kiện có side effect, cả **thứ tự thao tác**.

Không cần ép mọi phân loại thành một biểu thức điều kiện `?:` lồng dài. Chuỗi `if/else if` rõ thường phù hợp hơn khi có từ ba nhánh, kiểm tra đầu vào hoặc xử lý ngoại lệ.

## 12. Chương trình Java 17 chạy độc lập

Lưu đúng tên file **`IfBoundaryBranchOrderDemo.java`**:

~~~java
public final class IfBoundaryBranchOrderDemo {
    private IfBoundaryBranchOrderDemo() {}

    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        }
        if (score >= 90) {
            return "A";
        } else if (score >= 70) {
            return "B";
        } else if (score >= 50) {
            return "C";
        }
        return "D";
    }

    static String ageGroup(int age) {
        if (age >= 65) {
            return "SENIOR";
        } else if (age >= 18) {
            return "ADULT";
        }
        return "MINOR";
    }

    static String wrongAgeGroup(int age) {
        if (age >= 18) {
            return "ADULT";
        } else if (age >= 65) {
            return "SENIOR";
        }
        return "MINOR";
    }

    static int shippingFee(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        if (amount >= 500_000) {
            return 0;
        } else if (amount >= 200_000) {
            return 15_000;
        }
        return 30_000;
    }

    static String elementOrError(int[] values, int index) {
        if (values == null || index < 0 || index >= values.length) {
            return "OUT_OF_RANGE";
        }
        return Integer.toString(values[index]);
    }

    static boolean check(String name, boolean answer) {
        System.out.println("checked " + name);
        return answer;
    }

    public static void main(String[] args) {
        int[] testScores = {-1, 0, 49, 50, 69, 70, 89, 90, 100, 101};
        for (int score : testScores) {
            System.out.println("score " + score + "=" + grade(score));
        }

        System.out.println("age 17=" + ageGroup(17));
        System.out.println("age 18=" + ageGroup(18));
        System.out.println("age 65=" + ageGroup(65));
        System.out.println("wrong age 70=" + wrongAgeGroup(70));
        System.out.println("right age 70=" + ageGroup(70));

        System.out.println("fee 199999=" + shippingFee(199_999));
        System.out.println("fee 200000=" + shippingFee(200_000));
        System.out.println("fee 499999=" + shippingFee(499_999));
        System.out.println("fee 500000=" + shippingFee(500_000));

        int[] values = {10, 20, 30};
        System.out.println("index -1=" + elementOrError(values, -1));
        System.out.println("index 0=" + elementOrError(values, 0));
        System.out.println("index 2=" + elementOrError(values, 2));
        System.out.println("index 3=" + elementOrError(values, 3));
        System.out.println("index null=" + elementOrError(null, 0));

        double sum = 0.1 + 0.2;
        System.out.println("double sum=" + sum);
        System.out.println("double at most 0.3=" + (sum <= 0.3));
        System.out.println("NaN valid ratio=" + isValidRatio(Double.NaN));

        if (check("first", false)) {
            System.out.println("chosen=first");
        } else if (check("second", true)) {
            System.out.println("chosen=second");
        } else if (check("third", true)) {
            System.out.println("chosen=third");
        } else {
            System.out.println("chosen=else");
        }

        Boolean permission = null;
        if (Boolean.TRUE.equals(permission)) {
            System.out.println("permission=ALLOWED");
        } else {
            System.out.println("permission=DENIED");
        }
    }

    static boolean isValidRatio(double ratio) {
        return Double.isFinite(ratio)
                && ratio >= 0.0
                && ratio <= 1.0;
    }
}
~~~

**Yêu cầu:** JDK 17+, terminal ở thư mục chứa file; chỉ dùng JDK tiêu chuẩn.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfBoundaryBranchOrderDemo.java
java -cp . IfBoundaryBranchOrderDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfBoundaryBranchOrderDemo.java
java -cp . IfBoundaryBranchOrderDemo
~~~

**Exact expected stdout:**

~~~text
score -1=INVALID
score 0=D
score 49=D
score 50=C
score 69=C
score 70=B
score 89=B
score 90=A
score 100=A
score 101=INVALID
age 17=MINOR
age 18=ADULT
age 65=SENIOR
wrong age 70=ADULT
right age 70=SENIOR
fee 199999=30000
fee 200000=15000
fee 499999=15000
fee 500000=0
index -1=OUT_OF_RANGE
index 0=10
index 2=30
index 3=OUT_OF_RANGE
index null=OUT_OF_RANGE
double sum=0.30000000000000004
double at most 0.3=false
NaN valid ratio=false
checked first
checked second
chosen=second
permission=DENIED
~~~

Giải thích nhanh:

- `score 50`, `70`, `90` đi vào nhóm bắt đầu **ngay tại ngưỡng** nhờ `>=`.
- `wrong age 70=ADULT` cho thấy nhánh rộng `age >= 18` đã che khuất nhánh `age >= 65`.
- Mức phí giao hàng giảm đúng tại 200.000 và 500.000, không giảm trước ngưỡng.
- Chỉ số 3 bằng `values.length` nên bị loại.
- `0.1+0.2` vượt literal `0.3` một sai số nhị phân nhỏ, và `NaN` bị kiểm tra hữu hạn từ chối.
- Chỉ có `checked first` và `checked second`; điều kiện thứ ba không được gọi.
- `Boolean.TRUE.equals(null)` cho false, không unbox null.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách tránh |
|---|---|---|
| Dùng `score > 90` khi 90 thuộc hạng A | Bỏ sót đúng biên | `score >= 90` |
| Đặt `score >= 50` trước `score >= 90` | Giá trị 90 bị nhánh C nhận trước | Xếp ngưỡng theo thứ tự phù hợp |
| Dùng `else if` cho hai tính chất đều cần báo | Chỉ nhánh đúng đầu tiên chạy | Dùng hai `if` độc lập |
| Dùng nhiều `if` khi chỉ muốn một nhãn | Có thể chạy nhiều nhánh | Dùng chuỗi `else if` |
| Không validate `score > 100` | Điểm 101 bị nhận thành A | Kiểm tra miền trước |
| Dùng `index <= array.length` | Off-by-one, có thể lỗi truy cập | `index < array.length` |
| Viết `18 <= age <= 65` | Không hợp lệ trong Java | `age >= 18 && age <= 65` |
| Xem `else` thuộc `if` bên ngoài tùy ý | Dangling else gắn với if gần nhất | Dùng `{ }` |
| Chuyển thứ tự điều kiện có side effect | Đổi thứ tự gọi method/lỗi runtime | Tách side effect, giữ thứ tự |
| Giả định `double` so biên như thập phân chính xác | Sai số tính toán | Chọn mô hình/dung sai theo yêu cầu |
| Chỉ kiểm tra `ratio < 0 \|\| ratio > 1` | `NaN` có thể lọt | `Double.isFinite(ratio)` |
| Tính `max+1` gần `Integer.MAX_VALUE` để test | Overflow | Dùng kiểm thử biểu diễn hợp lệ |
| Chỉ kiểm tra giá trị giữa khoảng | Bỏ sót lỗi tại hai đầu | Test dưới/đúng/trên ngưỡng |

## 14. Bài tập có đáp án

### Bài A — xếp loại từ ngưỡng cao xuống thấp

Yêu cầu: `score >= 80` → GOOD, `score >= 50` → PASS, còn lại → FAIL.

~~~java
String label;
if (score >= 80) {
    label = "GOOD";
} else if (score >= 50) {
    label = "PASS";
} else {
    label = "FAIL";
}
~~~

**Đáp án tại biên:** 49 → FAIL; 50 → PASS; 79 → PASS; 80 → GOOD. Nếu miền hợp lệ riêng (ví dụ 0–100), cần validate trước.

### Bài B — vì sao `age >= 18` trước `age >= 65` sai?

**Đáp án:** tuổi 65 trở lên đã thỏa `age >= 18`, nên nhánh senior phía sau không được xét. Đặt `age >= 65` trước.

### Bài C — hai `if` hay `else if`?

Muốn in **cả** `positive` và `even` cho số 4:

~~~java
if (number > 0) System.out.println("positive");
if (number % 2 == 0) System.out.println("even");
~~~

**Đáp án:** cần hai `if` độc lập, vì cả hai điều kiện có thể đồng thời đúng. Nếu dùng `else if`, chỉ in `positive`.

### Bài D — kiểm tra chỉ số mảng

Mảng có ba phần tử, chỉ số hợp lệ là bao nhiêu?

**Đáp án:** `0`, `1`, `2`; điều kiện `index >= 0 && index < 3`. Chỉ số -1 và 3 đều bị loại.

### Bài E — thứ tự thực hiện nhánh

~~~java
if (check("A", false)) {
    System.out.println("A");
} else if (check("B", true)) {
    System.out.println("B");
} else if (check("C", true)) {
    System.out.println("C");
}
~~~

**Đáp án:**

~~~text
checked A
checked B
B
~~~

Method `check` lấy từ chương trình đầy đủ. Không gọi `check("C", true)`.

## 15. Checklist và kết luận

- [ ] Xác định rõ miền hợp lệ và ý nghĩa đúng tại từng biên.
- [ ] Dùng `>`/`>=`, `<`/`<=` theo đặc tả.
- [ ] Hiểu `if/else if/else` xét từ trên xuống và dừng ở **nhánh đúng đầu tiên**.
- [ ] Phân biệt chuỗi `else if` với nhiều câu `if` độc lập.
- [ ] Xếp điều kiện rộng/hẹp hoặc ưu tiên nghiệp vụ sao cho không che nhánh cần thiết.
- [ ] Validate giá trị ngoài miền trước khi phân loại.
- [ ] Xây dựng bảng test tại **dưới/đúng/trên** từng ngưỡng, gồm hai biên toàn miền.
- [ ] Không viết so sánh dây chuyền kiểu `min <= value <= max` trong Java.
- [ ] Dùng `{ }` để tránh dangling else.
- [ ] Không bỏ qua tác động của thứ tự nhánh lên side effect và ngoại lệ.
- [ ] Dùng guard `&&`/`||` đúng thứ tự trước truy cập có thể lỗi.
- [ ] Cẩn thận với `double` tại biên, NaN và overflow trong test số nguyên cực trị.
- [ ] Chạy `IfBoundaryBranchOrderDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Viết `if` đúng không chỉ là tạo điều kiện trả true/false; còn phải **định nghĩa ranh giới**, **ưu tiên nhánh**, **bao phủ miền dữ liệu** và **kiểm tra các giá trị sát ngưỡng**. Với chuỗi `else if`, thứ tự chính là một phần của logic nghiệp vụ. Đặt điều kiện có chủ đích và kiểm thử tại biên sẽ tránh được cả lỗi *off-by-one* lẫn nhánh bị che khuất.