# Đọc và ghi thuộc tính khi mô hình AOP hỗ trợ

Một đối tượng thường lưu trạng thái trong các **trường dữ liệu (fields)** và cung cấp cách truy cập trạng thái qua **thuộc tính (properties)** hoặc phương thức. Một số mô hình lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP) cho phép chọn **điểm đọc** và **điểm ghi** trường dữ liệu làm điểm can thiệp (join point). Khi đó, khía cạnh (aspect) có thể thực hiện hành vi bổ sung ngay quanh việc lấy hoặc gán một giá trị, ví dụ ghi nhận truy cập, quan sát thay đổi trạng thái hay kiểm tra một chính sách kỹ thuật.

Điểm mấu chốt của bài: **không phải cơ chế AOP nào cũng hỗ trợ điểm đọc/ghi trường dữ liệu**. Một cơ chế chỉ bao quanh lời gọi phương thức có thể theo dõi `getScore()` và `setScore(...)`, nhưng không vì thế mà theo dõi được lệnh `object.score` hoặc `object.score = ...`. Ta cần phân biệt loại điểm nối, đường thực thi thực tế và cơ chế kết hợp aspect (weaving).

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt trường dữ liệu, thuộc tính, getter/setter và **sự kiện đọc/ghi** ở cấp ngôn ngữ.
- Xác định khi nào một thao tác đọc hoặc ghi được mô hình AOP coi là join point.
- Giải thích pointcut chọn **field get** hoặc **field set** và advice có thể chạy trước, sau hoặc bao quanh thao tác được chọn như thế nào.
- Nhận diện khác biệt giữa chặn **truy cập trường trực tiếp** và chặn **lời gọi phương thức truy cập**.
- Hiểu vai trò của compile-time, binary và load-time weaving đối với khả năng can thiệp vào bytecode truy cập trường.
- Tránh các lỗi thường gặp về điểm can thiệp bị bỏ sót, lặp can thiệp, vòng lặp trong advice, trạng thái bất biến, hiệu năng và đồng thời.
- Kiểm thử một chính sách theo dõi đọc/ghi mà không vô tình đổi kết quả nghiệp vụ.

## 2. Phân biệt field, property và thao tác truy cập

Trong Java, **field** là biến được khai báo trong lớp hoặc đối tượng:

```java
class Device {
    int temperature;
}
```

Ở nơi có quyền truy cập, biểu thức `device.temperature` đọc field; câu lệnh `device.temperature = 25` ghi field. Đây là **truy cập trường trực tiếp**.

Một đối tượng cũng có thể bảo vệ trạng thái qua phương thức:

```java
class Device {
    private int temperature;

    public int getTemperature() {
        return temperature;
    }

    public void setTemperature(int value) {
        if (value < -50 || value > 150) {
            throw new IllegalArgumentException("Ngoài giới hạn");
        }
        temperature = value;
    }
}
```

Ở đây có hai lớp ý nghĩa:

1. Người sử dụng gọi `device.getTemperature()` hoặc `device.setTemperature(25)`: đó là **lời gọi phương thức**.
2. Bên trong phương thức, JVM thực hiện lệnh đọc hoặc ghi `temperature`: đó là **truy cập field**.

Một mô hình AOP có khả năng chọn điểm nối **method execution/method call** có thể quan sát lớp thứ nhất. Một mô hình hỗ trợ **field get/field set** có thể quan sát lớp thứ hai. Hai lớp có thể cùng xuất hiện trong một lần gọi; nếu đồng thời áp khía cạnh ở cả hai, sự kiện có thể bị ghi nhận hai lần nếu thiết kế không tính đến.

### 2.1. “Thuộc tính” không nhất thiết tương ứng một field

Từ *property* thường diễn tả một đặc điểm logic của đối tượng. Trong Java, property có thể được biểu diễn qua cặp getter/setter theo quy ước đặt tên, nhưng không nhất thiết có field cùng tên:

```java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    public int getArea() {
        return width * height;
    }
}
```

`getArea()` cung cấp thuộc tính suy ra từ hai field. Không có field `area` để một pointcut chọn theo thao tác đọc `area`. Tương tự, một setter có thể cập nhật nhiều field, gửi sự kiện hoặc từ chối ghi. Chặn lời gọi getter/setter và chặn bytecode đọc/ghi field vì vậy **không thể thay thế nhau một cách máy móc**.

### 2.2. Đọc và ghi là hai hành vi khác nhau

| Trường hợp | Ví dụ | Hành vi quan sát |
| --- | --- | --- |
| Đọc field | `int x = device.temperature;` | Lấy giá trị hiện tại của field |
| Ghi field | `device.temperature = 25;` | Đưa một giá trị mới vào field |
| Gọi getter | `int x = device.getTemperature();` | Chạy phương thức, có thể bao gồm một hay nhiều lần đọc field |
| Gọi setter | `device.setTemperature(25);` | Chạy phương thức, có thể kiểm tra, biến đổi rồi ghi field |
| Đọc thuộc tính tính toán | `rectangle.getArea();` | Chạy logic tính giá trị, không đòi hỏi field cùng tên |

Với Java, một biểu thức có cả đọc và ghi như `counter.value++` thường cần **đọc giá trị hiện tại rồi ghi giá trị mới**. Nếu mô hình và điểm biến đổi tương ứng hỗ trợ cả hai, một câu lệnh nguồn có thể tạo **hơn một điểm can thiệp**. Không nên đếm số sự kiện bằng số dòng mã.

## 3. Điểm đọc/ghi trong mô hình AOP

### 3.1. Join point: điểm có thể can thiệp

**Join point** là vị trí thực thi được mô hình AOP nhận diện và cho phép gắn hành vi bổ sung. Với một cơ chế hỗ trợ truy cập trường, nó có thể bao gồm:

- **Field get:** thời điểm mã đang lấy một giá trị từ field.
- **Field set:** thời điểm mã đang gán giá trị cho field.
- Các loại điểm khác, nếu công nghệ hỗ trợ, như thực thi phương thức, tạo đối tượng, xử lý ngoại lệ.

Không nên suy luận rằng một công nghệ hỗ trợ field get thì tự động hỗ trợ mọi dạng quan sát đọc trạng thái. Chẳng hạn, một lời gọi reflection, một thao tác native, một truy cập qua phương thức đặc biệt hoặc một đường thực thi không nằm trong phạm vi biến đổi có thể có quy tắc khác. **Tập join point do cơ chế AOP và cách weaving xác định**, không chỉ do cú pháp Java.

### 3.2. Pointcut: chọn những thao tác nào

**Pointcut** là quy tắc chọn join point. Với truy cập field, một pointcut có thể dựa trên:

- Tên field, kiểu dữ liệu, lớp khai báo và phạm vi lớp/gói;
- Field tĩnh hoặc thuộc đối tượng, nếu mô hình cho phép phân biệt;
- Thao tác đọc hay ghi;
- Ngữ cảnh của đường thực thi, đối tượng đang được truy cập hoặc những điều kiện động được cơ chế hỗ trợ;
- Quy tắc loại trừ mã của chính khía cạnh và các phần không cần quan sát.

Pointcut quá rộng như “mọi truy cập mọi field” có thể tạo lượng advice rất lớn và dễ quan sát cả trạng thái nội bộ của thư viện. Pointcut quá hẹp có thể bỏ sót đường ghi quan trọng. Tốt hơn nên xác định rõ **field nào**, **thao tác nào** và **ở ranh giới nào** thực sự cần chính sách.

### 3.3. Advice: hành vi cần kết hợp

**Advice** là hành vi được thực hiện tại điểm đã chọn, ví dụ:

| Kiểu advice | Khi áp dụng vào đọc/ghi | Điểm cần lưu ý |
| --- | --- | --- |
| Trước (before) | Ghi nhận sắp đọc hoặc sắp ghi | Với ghi, việc “sắp ghi” chưa chứng minh gán đã thành công |
| Sau thành công (after returning) | Ghi nhận thao tác đã kết thúc bình thường | Chỉ phản ánh kết quả theo đường thành công, không phải mọi nhánh lỗi |
| Sau lỗi (after throwing) | Theo dõi ngoại lệ liên quan điểm truy cập | Truy cập field đơn giản có ít đường lỗi hơn một phương thức nghiệp vụ |
| Cuối cùng (after/finally) | Thu dọn bối cảnh đo đạc trên nhiều nhánh | Ngữ nghĩa chính xác phụ thuộc mô hình advice |
| Bao quanh (around) | Có thể điều phối thao tác đọc/ghi hoặc kết quả | Có nguy cơ ngăn thao tác, đổi giá trị, thực hiện lặp hoặc gây lỗi |

Một số công nghệ chỉ hỗ trợ một tập con kiểu advice cho từng loại điểm nối hoặc có quy tắc ràng buộc kiểu kết quả/đối số. Không giả định mọi advice đều hợp lệ với mọi field.

### 3.4. Weaving: biến quy tắc thành hành vi thực

Một mô tả pointcut và advice không tự nhiên làm mọi phép đọc/ghi trong chương trình được giám sát. **Weaving** kết hợp khía cạnh vào chương trình sao cho tại những điểm được hỗ trợ, hành vi bổ sung chạy đúng chỗ.

Một số công cụ biến đổi mã nguồn hoặc bytecode tại giai đoạn biên dịch/sau biên dịch; một số cho phép biến đổi trước khi JVM định nghĩa lớp; một số chỉ tổ chức các bộ chặn lời gọi quanh đối tượng. Những lựa chọn này ảnh hưởng trực tiếp đến việc field get/set có được quan sát hay không.

## 4. Khi field get/set là join point, chuyện gì xảy ra?

Giả sử một chương trình có:

```java
class Meter {
    int reading;
}

Meter meter = new Meter();
meter.reading = 42;
int current = meter.reading;
```

Đây là **đoạn mã minh họa**, không phải một tệp chạy độc lập.

Nếu công cụ có thể can thiệp vào truy cập trường và pointcut chọn đúng `Meter.reading`, quy tắc được hiểu theo ý tưởng:

```text
meter.reading = 42
         |
         v
[Pointcut có chọn field set của Meter.reading?]
         |
        Có
         |
         v
[Advice trước ghi, nếu có]
         |
         v
[Thao tác ghi giá trị 42]
         |
         v
[Advice sau ghi, nếu có]

int current = meter.reading
                   |
                   v
[Pointcut có chọn field get của Meter.reading?]
                   |
                  Có
                   |
                   v
[Advice trước đọc, nếu có]
                   |
                   v
[Thao tác lấy giá trị]
                   |
                   v
[Advice sau đọc, nếu có]
```

Một lớp biến đổi bytecode có thể chèn lệnh phục vụ advice quanh chính các lệnh truy cập field tương ứng. Điều đó khác với việc yêu cầu tất cả người gọi viết `audit(...)` thủ công.

### 4.1. Field read và giá trị quan sát được

Khi một thao tác đọc đã có kết quả, **after returning** có thể giúp quan sát giá trị trả về *nếu công nghệ hỗ trợ kết nối kết quả vào advice*. Nhưng giá trị ấy không nhất thiết là “giá trị mới nhất trên toàn hệ thống” trong môi trường nhiều luồng; cách nhìn thấy giá trị còn phụ thuộc mô hình bộ nhớ.

Nếu **around advice** được phép thay kết quả của phép đọc, chương trình có thể nhìn thấy giá trị khác với giá trị thực đang lưu. Đây là thay đổi có thể ảnh hưởng quy tắc nghiệp vụ và bất biến, không còn là quan sát thuần túy.

### 4.2. Field write và trạng thái trước/sau

Trước khi ghi, một advice có thể thấy thông tin về field, đối tượng hoặc giá trị định ghi **nếu điểm nối và cơ chế hỗ trợ truyền dữ liệu đó**. Tuy nhiên:

- Giá trị định ghi chưa chắc trở thành giá trị đã lưu: thao tác có thể bị chặn, lỗi hoặc biến đổi;
- Đọc lại field để tìm giá trị cũ có thể làm nảy sinh **một join point đọc khác**, dẫn đến ghi log lặp hoặc vòng lặp nếu không loại trừ;
- Trong môi trường đồng thời, đọc “giá trị cũ” ở một thời điểm rồi so sánh với “giá trị mới” ở thời điểm khác **không bảo đảm hai giá trị tạo thành một chuyển trạng thái nguyên tử**;
- Một advice chạy sau thao tác ghi không tự biến thao tác thành một giao dịch có thể hoàn tác.

Nếu cần sự kiện “trạng thái đã chuyển chính xác từ A sang B”, hãy xác định thao tác cập nhật nguyên tử hoặc ranh giới nghiệp vụ tạo sự kiện đó. Một quan sát field set đơn thuần chưa cung cấp toàn bộ cam kết này.

### 4.3. Cùng một trạng thái có nhiều đường truy cập

Một field riêng tư có thể được ghi trong constructor, setter, phương thức nội bộ, hoặc qua cơ chế truy cập đặc biệt. Trường hợp nào phát sinh join point và thực sự được weaving phải được xác minh.

Chẳng hạn:

```java
class Account {
    private int balance;

    Account(int openingBalance) {
        this.balance = openingBalance;
    }

    void deposit(int amount) {
        this.balance += amount;
    }

    int balance() {
        return this.balance;
    }
}
```

Trong đoạn trên, `deposit` thường có cả đọc và ghi `balance`; constructor có ghi; phương thức `balance()` có đọc. Nếu bộ weaving chọn thao tác field get/set và có quyền biến đổi mã tương ứng, có thể có nhiều điểm can thiệp. Nếu cơ chế chỉ quan sát lời gọi `deposit()` hay `balance()`, đó là **điểm can thiệp phương thức**, với khả năng bao quát khác.

## 5. Phân biệt hai đường kỹ thuật: field weaving và proxy getter/setter

| Tiêu chí | Field get/set weaving (khi hỗ trợ) | Chặn getter/setter qua proxy/interceptor |
| --- | --- | --- |
| Điểm được chọn | Thao tác đọc/ghi một field trong phần mã có thể can thiệp | Lời gọi phương thức như `getValue()` hoặc `setValue(...)` |
| Người gọi trực tiếp truy cập field | Có thể được can thiệp nếu đường bytecode đó đã được kết hợp và được hỗ trợ | Không đi qua getter/setter nên không bị proxy getter/setter quan sát |
| Tự gọi phương thức trong đối tượng | Field access bên trong có thể được can thiệp khi mã chứa access đã được biến đổi | Lời gọi qua `this` thường không đi qua proxy ngoài |
| Getter tính toán giá trị | Không có field logic tương ứng thì không tồn tại field get để chọn | Vẫn có thể quan sát lời gọi getter |
| Phạm vi kỹ thuật | Thường đòi hỏi cơ chế weaving sửa mã/bytecode trong phạm vi hỗ trợ | Có thể tổ chức động theo đối tượng đại diện hoặc chuỗi bộ chặn |
| Ngữ nghĩa | Quan sát một truy cập lưu trữ cụ thể | Quan sát một thao tác do API của đối tượng định nghĩa |
| Rủi ro thường gặp | Quá nhiều join point, hiệu năng, recursion, bỏ sót đường truy cập không biến đổi | Đường gọi bypass, proxy khác identity, setter không ghi đúng một field |

**Không đồng nhất** “phương thức `getX()` được gọi” với “field `x` đã được đọc”. Một getter có thể trả về hằng số, tính toán, đọc bộ nhớ đệm, gọi dịch vụ khác hoặc ném lỗi; một setter có thể từ chối gán hoặc thay đổi nhiều field.

### 5.1. Một giới hạn căn bản của JDK dynamic proxy

Trong Java, JDK dynamic proxy thông thường nhận cuộc gọi **qua những phương thức giao diện**. Nó không tự can thiệp lệnh `obj.field`, `obj.field = value`, constructor hay toàn bộ hành vi nội bộ của lớp đích.

Vì vậy một ví dụ chỉ sử dụng proxy cho getter/setter **không phải bằng chứng đã weaving các điểm field get/set**. Ta có thể học cách tách hành vi quan sát từ proxy, nhưng phải diễn giải chính xác lớp hành vi đang được quan sát.

## 6. Ví dụ Java 17 chạy được: quan sát truy cập qua getter/setter

Ví dụ dùng JDK dynamic proxy để minh họa một phương án **theo dõi truy cập thuộc tính qua API phương thức**. Phần dữ liệu thật vẫn nằm trong lớp `Score`, còn lớp bọc chỉ ghi nhận hoạt động. Ví dụ không yêu cầu thư viện ngoài JDK.

Lưu vào tệp `PropertyAccessDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class PropertyAccessDemo {
    interface ScorePort {
        int getScore();
        void setScore(int next);
    }

    static final class Score implements ScorePort {
        private int score = 10;

        @Override
        public int getScore() {
            return score;
        }

        @Override
        public void setScore(int next) {
            if (next < 0) {
                throw new IllegalArgumentException("Điểm phải không âm");
            }
            score = next;
        }
    }

    static Object invoke(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static ScorePort observe(ScorePort target) {
        return (ScorePort) Proxy.newProxyInstance(
                ScorePort.class.getClassLoader(),
                new Class<?>[] { ScorePort.class },
                (proxy, method, args) -> {
                    String name = method.getName();
                    boolean reading = name.equals("getScore");
                    boolean writing = name.equals("setScore");

                    if (reading) {
                        System.out.println("[READ] begin");
                    }
                    if (writing) {
                        System.out.println("[WRITE] requested=" + args[0]);
                    }

                    try {
                        Object result = invoke(method, target, args);
                        if (reading) {
                            System.out.println("[READ] ok");
                        }
                        if (writing) {
                            System.out.println("[WRITE] ok");
                        }
                        return result;
                    } catch (Throwable ex) {
                        if (writing) {
                            System.out.println("[WRITE] rejected");
                        }
                        throw ex;
                    }
                });
    }

    public static void main(String[] args) {
        Score real = new Score();
        ScorePort observed = observe(real);

        System.out.println("Điểm ban đầu: " + observed.getScore());
        observed.setScore(12);
        System.out.println("Điểm mới: " + observed.getScore());

        try {
            observed.setScore(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        System.out.println("Đọc trực tiếp: " + real.getScore());
    }
}
```

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

```bash
javac PropertyAccessDemo.java
java PropertyAccessDemo
```

Đầu ra:

```text
[READ] begin
[READ] ok
Điểm ban đầu: 10
[WRITE] requested=12
[WRITE] ok
[READ] begin
[READ] ok
Điểm mới: 12
[WRITE] requested=-1
[WRITE] rejected
Lỗi: Điểm phải không âm
Đọc trực tiếp: 12
```

**Giải thích chính xác cơ chế:**

1. `Score` sở hữu trạng thái và **bất biến nghiệp vụ**: điểm không được âm. Proxy không thay đổi quy tắc này.
2. `observe(real)` tạo đối tượng đại diện. Người gọi sử dụng `observed` sẽ đi qua logic ghi nhận trước và sau lời gọi getter/setter.
3. `method.invoke(...)` dùng reflection chuyển lời gọi tới đối tượng thật. `InvocationTargetException` được bóc để giữ lại ngoại lệ `IllegalArgumentException` do `Score.setScore` ném ra.
4. Việc ghi thất bại in `[WRITE] rejected`, và lỗi vẫn đến người gọi. Giá trị trong `Score` giữ nguyên `12`; lần đọc trực tiếp cuối cho thấy điều đó.
5. `real.getScore()` gọi trực tiếp đối tượng đích nên không đi qua proxy, vì vậy **không phát sinh** dòng `[READ]`. Đây là ranh giới can thiệp của proxy; không phải lỗi trong ví dụ.
6. Ở đây các pointcut đơn giản được mô phỏng bằng tên phương thức; ví dụ **không chặn trực tiếp lệnh đọc/ghi field `score`**.

Trong ứng dụng thật, ghi mọi giá trị thuộc tính vào log có thể để lộ thông tin nhạy cảm. Các thông tin như mật khẩu, token, dữ liệu cá nhân hoặc khóa bí mật phải được loại bỏ hay che chắn theo chính sách thích hợp.

## 7. Ví dụ mô hình có field join point: cú pháp AspectJ để đối chiếu

Để nhìn thấy **một công nghệ thực sự biểu đạt điểm đọc/ghi field**, ta có thể dùng cú pháp khía cạnh của AspectJ như một ví dụ cụ thể. Cú pháp `get(...)` và `set(...)` trong phần này thuộc **mô hình điểm nối của AspectJ**; đó không phải cú pháp Java tiêu chuẩn và không phải cam kết mọi hệ AOP đều hỗ trợ.

Mã đối tượng đích, tệp `FieldDemo.java`:

```java
public class FieldDemo {
    public int score;

    public static void main(String[] args) {
        FieldDemo example = new FieldDemo();
        example.score = 7;
        System.out.println("Score=" + example.score);
    }
}
```

Khía cạnh, tệp `ScoreFieldAspect.aj`:

```java
public aspect ScoreFieldAspect {
    before(): set(int FieldDemo.score) {
        System.out.println("[FIELD] set");
    }

    before(): get(int FieldDemo.score) {
        System.out.println("[FIELD] get");
    }
}
```

Đây là **hai tệp dùng bộ biên dịch/weaver AspectJ phù hợp**, không phải chương trình có thể biên dịch `ScoreFieldAspect.aj` bằng `javac` thông thường. Nếu khía cạnh được weaving vào đúng các thao tác trong `FieldDemo.main`, đầu ra là:

```text
[FIELD] set
[FIELD] get
Score=7
```

Nếu chỉ biên dịch và chạy `FieldDemo.java` bằng Java thuần, không có bước weaving, đầu ra chỉ là:

```text
Score=7
```

Điểm cần quan sát: `example.score = 7` là một lần **ghi field trực tiếp**, còn `example.score` trong phép in là **đọc field trực tiếp**. Ở ví dụ này, việc chọn chúng dựa vào kiểu field và lớp khai báo, không dựa vào tên getter/setter. `public` được dùng để ví dụ ngắn, **không phải khuyến nghị công khai trạng thái đối tượng** trong thiết kế thông thường.

### 7.1. Cần điều kiện nào để ví dụ field weaving có hiệu lực?

- Có bộ weaving thực sự hiểu và hỗ trợ loại join point `get`/`set`;
- Đã cung cấp aspect và mã chứa thao tác truy cập vào đúng quy trình kết hợp;
- Điểm truy cập được công cụ nhận diện và không bị loại trừ theo cấu hình;
- Artifact hoặc lớp đã được kết hợp là bản chương trình thật sự được chạy.

Không nên gán đầu ra `[FIELD]...` cho Java/JVM mặc định: chính **cơ chế aspect** tạo ra hành vi bổ sung này.

### 7.2. Điều gì không được suy ra từ ví dụ?

Ví dụ không chứng minh mọi lệnh reflection, `VarHandle`, lệnh native hoặc truy cập do thư viện bên ngoài sinh ra đều phát sinh cùng các join point. Nó cũng không chứng minh mọi bộ weaving đều có quyền sửa mọi lớp, mọi module hoặc mọi đoạn bytecode.

Một số cơ chế kết hợp mã có thể chặn các lệnh đọc/ghi field trong bytecode đã được weaving; một cơ chế chỉ bọc phương thức sẽ không tự đạt khả năng đó. **Phạm vi can thiệp phải được kiểm chứng bằng đường chạy thực tế của công cụ được chọn.**

## 8. Áp dụng vào những mối quan tâm nào?

Không phải mọi phép đọc/ghi thuộc tính đều có ý nghĩa như nhau. Việc chọn AOP hợp lý khi một **chính sách cắt ngang** cần áp dụng nhất quán ở nhiều điểm, còn bất biến và quy tắc nghiệp vụ vẫn có chỗ sở hữu rõ ràng.

| Nhu cầu | Có thể làm bằng advice khi hỗ trợ | Giới hạn cần giữ |
| --- | --- | --- |
| Đếm số lần đọc một nhóm field để phân tích hiệu năng | Tăng bộ đếm mỗi lần field get được quan sát | Không suy ra số lần đọc vật lý từ bộ nhớ/JIT hoặc mọi đường truy cập |
| Theo dõi truy cập trạng thái nhạy cảm | Ghi loại thao tác và bối cảnh tối thiểu | Không ghi giá trị bí mật; cần kiểm soát quyền ở ranh giới đáng tin cậy |
| Chẩn đoán thay đổi trạng thái | Ghi dấu vết lúc field set | Không tự bảo đảm giao dịch hoặc sự kiện nghiệp vụ đã xác nhận |
| Thực thi một chính sách kỹ thuật tại nhiều setter | Chặn lời gọi setter trong phạm vi được chọn | Không thay bất biến miền nghiệp vụ hoặc bỏ sót đường ghi khác |
| Đo tần suất truy cập | Ghi số lượng, lớp/field, khoảng thời gian | Tránh overhead lớn và quan sát trùng |
| Thu thập sự kiện vận hành | Phát thông tin kỹ thuật từ điểm đã hỗ trợ | Bảo vệ độ tin cậy và tránh làm thao tác chính hỏng vì log |

### 8.1. Phân biệt kiểm tra miền nghiệp vụ với quan sát kỹ thuật

Ví dụ “số dư không được âm” là bất biến cần được bảo vệ bởi phần sở hữu dữ liệu, giao dịch hoặc ranh giới miền nghiệp vụ thích hợp. Đưa điều kiện này **chỉ vào field-set advice** có thể không đủ nếu có đường ghi ngoài phạm vi weaving, đặc biệt khi dữ liệu còn thay đổi trong cơ sở dữ liệu hoặc hệ thống khác.

Ngược lại, việc đếm số lần truy cập cho mục đích theo dõi vận hành là ứng viên tự nhiên cho một hành vi cắt ngang, với điều kiện chi phí và việc chọn đúng điểm được kiểm soát.

### 8.2. Ghi nhận field set không đồng nghĩa sự kiện nghiệp vụ

Một nghiệp vụ “đơn hàng chuyển sang đã thanh toán” thường cần thông tin danh tính đơn hàng, khoản tiền, trạng thái giao dịch, thời điểm xác nhận và độ tin cậy của việc phát sự kiện. Một field có thể được gán nhiều lần khi dựng, khôi phục hoặc sao chép đối tượng. Do đó `set(status)` ở cấp bộ nhớ không nhất thiết là **sự kiện chuyển trạng thái đã hoàn tất**.

Để phát sự kiện nghiệp vụ chính xác, hãy xuất phát từ thao tác miền nghiệp vụ hoặc ranh giới giao dịch đáng tin, rồi dùng khía cạnh cho phần hạ tầng phù hợp nếu cần.

## 9. Trường hợp nâng cao và các giới hạn khó nhận thấy

### 9.1. Đọc/ghi field `final`, bất biến và khởi tạo

Một field `final` có quy tắc gán theo ngôn ngữ và quá trình khởi tạo riêng. Một khía cạnh quan sát không nên mặc định có thể **thay một thao tác ghi bất biến** hoặc sửa field sau khi xây dựng đối tượng. Kể cả khi một công cụ báo có thể chọn điểm ghi trong giai đoạn khởi tạo, quyền thay đổi kết quả vẫn bị giới hạn bởi ngữ nghĩa Java và khả năng của bộ weaving.

Với đối tượng bất biến, các giá trị thường được thiết lập một lần rồi chỉ được đọc; việc ghi log mọi lần đọc có thể gây chi phí lớn mà không cung cấp thông tin nghiệp vụ mới.

### 9.2. Trường `static`, trạng thái dùng chung và số lượng sự kiện

Field `static` thuộc về lớp, không thuộc từng instance. Nếu pointcut chọn cả các truy cập `static`, bối cảnh join point có thể không có đối tượng nhận cụ thể. Advice không nên giả định luôn tìm được `this` hay đối tượng đích.

Một field được đọc trong vòng lặp lớn cũng có thể tạo **rất nhiều lần thực thi advice**. Nếu mỗi lần còn ghi log đồng bộ hoặc truy cập mạng, chính chính sách theo dõi có thể làm thay đổi rõ hiệu năng.

### 9.3. Đồng thời, `volatile` và Java Memory Model

Một truy cập field được quan sát bằng advice không tự thay đổi tính nguyên tử hoặc quy tắc hiển thị bộ nhớ của phép đọc/ghi gốc. Với field thường, luồng khác có thể không thấy cập nhật như mong đợi nếu chương trình thiếu quan hệ đồng bộ đúng. Với `volatile`, Java quy định những bảo đảm nhìn thấy và thứ tự nhất định, nhưng **`count++` vẫn không phải phép tăng nguyên tử** chỉ vì field là `volatile`.

Một advice định “đọc cũ rồi ghi mới” ở hai thời điểm không tự khóa được các luồng khác; số đo có thể không tạo thành ảnh chụp trạng thái nhất quán. Khi cần bất biến đồng thời, hãy dùng cấu trúc phù hợp như khóa, thao tác nguyên tử hoặc điều phối giao dịch, tùy miền vấn đề.

### 9.4. Advice tự đọc/ghi cùng field

Xét một advice cho mọi lần đọc `x`, rồi bên trong advice lại đọc `x` để ghi log. Nếu thao tác bên trong cũng khớp pointcut và được weaving, advice có thể tiếp tục gọi chính nó.

Cách phòng tránh có thể gồm:

- Loại trừ mã nằm trong chính aspect hoặc phần hạ tầng theo dõi khỏi pointcut, theo khả năng ngôn ngữ;
- Chọn một tập field hẹp và không thực hiện truy cập đó trong advice;
- Dùng cơ chế bảo vệ tái nhập (reentrancy) khi thực sự cần và thiết kế rõ phạm vi theo luồng/tác vụ;
- Chỉ lấy thông tin join point được cơ chế cung cấp thay vì đọc lại field nhiều lần.

Bảo vệ tái nhập cũng phải cẩn trọng với đa luồng và bất đồng bộ. Một biến cờ toàn cục dùng chung không phải lời giải an toàn cho mọi tình huống.

### 9.5. Hai aspect trên cùng một điểm

Một truy cập có thể khớp cả aspect đo thời gian và aspect kiểm toán. Nếu khía cạnh A bao quanh B, kết quả thường có cấu trúc **A(B(truy cập))**; đổi thứ tự có thể đổi điểm quan sát và cách xử lý lỗi. Không được mặc định thứ tự do tên tệp hoặc thứ tự khai báo quyết định.

Với advice chỉ quan sát, nên giữ nguyên kết quả đọc, giá trị ghi và ngoại lệ. Nếu around advice thực sự thay đổi giá trị, phải quy định rõ việc thay đổi và kiểm tra tác động lên những advice khác.

### 9.6. Reflection, `VarHandle`, native access và đường truy cập ngoài phạm vi

Những đường truy cập ngoài cú pháp field trực tiếp có thể thực hiện thông qua API đặc biệt. Một bộ weaving dựa trên **điểm bytecode của mã đã được biến đổi** không nhất thiết nhìn thấy thao tác diễn ra trong mã thư viện, JVM hoặc native. Tùy công cụ, một phần những đường ấy có thể can thiệp được, nhưng **không được giả định** chỉ vì tên field giống nhau.

Khi chính sách là điều kiện an toàn quan trọng, phải thống kê các đường có thể chạm trạng thái và kiểm tra trường hợp bypass. Nếu không thể kiểm soát chúng, cần một ranh giới bảo vệ khác.

### 9.7. Ảnh hưởng của compiler/JIT và phạm vi đo đạc

Source code có thể được biên dịch thành các lệnh bytecode nhất định; JVM có thể tối ưu trong lúc thực thi. Advice thêm hành vi quan sát được có thể thay đổi tối ưu và chi phí. Việc đếm advice ở các field join point **không tương đương phép đo số lần truy cập RAM hoặc CPU cache**.

Không sử dụng số đếm get/set như thước đo hiệu năng cấp phần cứng. Muốn phân tích hiệu năng, phải có thí nghiệm và công cụ đo phù hợp với mục đích.

## 10. Kiểm thử việc can thiệp đọc/ghi có hiệu lực

Một chính sách field get/set cần được kiểm tra bằng **mã thực sự thực thi thao tác truy cập** và trong đúng cấu hình weaving. Chỉ thấy pointcut được khai báo là chưa đủ.

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Ghi field được chọn | Advice ghi chạy đúng số lần và đúng thời điểm |
| Đọc field được chọn | Advice đọc chạy đúng số lần, không thay kết quả ngoài dự kiến |
| Field ngoài pointcut | Không phát sinh advice ngoài phạm vi |
| Getter có nhiều lần đọc field | Phân biệt số lần gọi getter với số field get |
| Setter từ chối dữ liệu | Không báo “ghi thành công” nếu setter thất bại |
| Ghi trong constructor/đường nội bộ | Quan sát đúng phạm vi mà cơ chế weaving hỗ trợ |
| Lời gọi qua proxy và bypass proxy | Hiểu điểm nào chỉ là method interception |
| Đọc/ghi đồng thời | Không lẫn bối cảnh, không hứa tính nguyên tử sai |
| Advice tự tham chiếu field | Không có vòng lặp hay đếm tăng bất thường |
| Chạy bằng artifact khác hoặc thiếu weaving | Phát hiện chính sách không được áp dụng |

### 10.1. Quy trình chẩn đoán khi thiếu sự kiện

1. **Phân loại thao tác:** đây là field get/set hay lời gọi getter/setter?
2. **Kiểm tra mô hình join point:** công cụ có hỗ trợ loại thao tác đang xét không?
3. **Kiểm tra pointcut:** tên field, kiểu, nơi khai báo, điều kiện động và loại trừ có khớp thực tế không?
4. **Kiểm tra phạm vi weaving:** mã thực hiện truy cập có được biên dịch/biến đổi/nạp đúng quy trình không?
5. **Kiểm tra đường gọi:** có bypass proxy, đọc trong lớp chưa được weaving, hoặc dùng API truy cập đặc biệt không?
6. **Kiểm tra nhiều khía cạnh:** có ghi trùng, chặn trước thao tác hay lỗi trong advice không?
7. **Kiểm tra kết quả:** số đo, giá trị sau ghi, ngoại lệ và ảnh hưởng đối với chức năng nghiệp vụ có đúng không?

### 10.2. Phân biệt quan sát với kiểm soát

Nếu mục tiêu là **chẩn đoán**, việc ghi nhận thiếu một nhóm truy cập có thể làm số liệu sai. Nếu mục tiêu là **kiểm soát quyền**, bỏ sót một đường truy cập có thể nghiêm trọng hơn: một lớp advice không bao trùm tất cả đường ghi không nên được xem là ranh giới bảo vệ duy nhất.

Từ đó, hãy chọn mô hình AOP dựa trên phạm vi và độ tin cậy yêu cầu, không chỉ dựa trên vẻ tiện lợi của cú pháp pointcut.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi mọi getter là một field get | Hiểu sai số lượng và vị trí join point | Tách khái niệm lời gọi phương thức và truy cập lưu trữ |
| Cho rằng proxy chặn được `obj.field` | Đường trực tiếp không được quan sát | Chọn cơ chế thật sự hỗ trợ field access hoặc thay API truy cập |
| Ghi “đã thay đổi” ngay trước field set | Có thể báo sự kiện chưa thành công | Phân biệt ý định ghi, thực thi ghi và xác nhận nghiệp vụ |
| Dùng pointcut chọn toàn bộ field | Số sự kiện quá lớn, rò rỉ dữ liệu | Giới hạn field/miền và loại trừ dữ liệu nhạy cảm |
| Advice tự đọc lại field đang bị giám sát | Recursion, lặp log, tràn stack | Giảm phạm vi pointcut hoặc loại trừ mã advice |
| Coi field set là giao dịch nguyên tử | Báo chuyển trạng thái sai dưới tải đồng thời | Đặt tính nhất quán ở nơi sở hữu bất biến |
| Dùng advice đổi kết quả đọc mà không xét nghiệp vụ | Người gọi nhìn thấy giá trị bất ngờ | Chỉ thay kết quả theo hợp đồng rõ, ưu tiên giữ nguyên với chính sách quan sát |
| Không kiểm tra đường đặc biệt | Thiếu sự kiện hoặc bỏ qua kiểm soát | Thống kê và thử các đường thực thi được hỗ trợ |
| Dựa vào tên aspect để suy ra khả năng | Hiểu sai mô hình của công cụ | Xác minh join point thực, giai đoạn weaving và artifact |

## 12. Bài tập vận dụng có đáp án

### Bài 1: Đếm các điểm can thiệp

Cho đoạn mã:

```java
class Box {
    int value;
}

Box box = new Box();
box.value = 3;
box.value++;
System.out.println(box.value);
```

Nếu **mô hình có hỗ trợ field get/set** và toàn bộ mã truy cập trên được weaving, có bao nhiêu điểm truy cập `value` được quan sát theo ý tưởng bytecode thông thường?

**Gợi ý đáp án:** Câu gán `box.value = 3` tạo một field set. Câu `box.value++` cần đọc giá trị cũ rồi ghi giá trị tăng lên, nên thường có một field get và một field set. Câu in `box.value` có một field get. Tổng: **2 lần đọc, 2 lần ghi**. Đây là cách phân tích mã Java trong trường hợp tiêu chuẩn và weaving phù hợp, không phải cam kết mọi công cụ/đường chạy có cùng số event nếu phạm vi điểm nối khác nhau.

### Bài 2: Phân biệt property và field

Một lớp khai báo `private int price`, nhưng `getPrice()` trả về `price + tax`. Pointcut chọn **lời gọi getter** có tương đương pointcut chọn **đọc field `price`** không?

**Đáp án:** Không. Getter trả về giá đã cộng thuế, còn field chứa giá gốc; getter có thể đọc nhiều field hoặc thực hiện tính toán. Hai pointcut có phạm vi và dữ liệu quan sát khác nhau.

### Bài 3: Tình huống proxy

Một chương trình dùng proxy để ghi log khi `setStatus(...)` được gọi. Phương thức `resetInternal()` trên đối tượng đích tự gán `this.status = "NEW"`. Vì sao không thấy log của setter?

**Đáp án:** Vì mã đang ghi field trực tiếp trong lớp, không gọi setter qua proxy. Proxy theo dõi lời gọi setter không tự theo dõi lệnh gán field; chỉ một cơ chế có điểm can thiệp field thực sự và weaving đúng phạm vi mới có thể quan sát đường này.

### Bài 4: Sự kiện nghiệp vụ

Một hệ thống phát sự kiện “Đơn đã giao” từ advice mỗi khi field `status` được ghi thành `DELIVERED`. Có thể xem đây là bằng chứng đơn hàng đã giao thành công không?

**Đáp án:** Chưa đủ. Trạng thái trong bộ nhớ có thể là tạm thời, được khôi phục từ dữ liệu cũ hoặc bị sửa trong tác vụ không thành công. Cần xác định sự kiện nghiệp vụ ở ranh giới có tính nhất quán và xác nhận tương ứng.

### Bài 5: Đồng thời

Hai luồng cùng thay đổi một field `counter`; advice đọc “giá trị trước” và “giá trị sau” để ghi nhận. Điều đó có bảo đảm mỗi log là một lần chuyển trạng thái duy nhất không?

**Đáp án:** Không. Hai lần đọc trong advice có thể xen kẽ với thay đổi của luồng khác. Phải thiết kế thao tác cập nhật nguyên tử hoặc đồng bộ phù hợp nếu yêu cầu một cặp trước–sau chính xác.

## 13. Ghi nhớ

- Một số mô hình AOP coi **đọc field (get)** và **ghi field (set)** là join point; nhiều cơ chế khác chỉ chặn **lời gọi phương thức**.
- **Field access** khác **getter/setter invocation**; một thuộc tính logic thậm chí có thể không có field tương ứng.
- Pointcut xác định **đúng vị trí đọc/ghi**, advice xác định **hành vi kèm theo**, weaving làm hành vi ấy có hiệu lực tại các điểm thực sự được hỗ trợ.
- Theo dõi field set **không tự bảo đảm** bất biến nghiệp vụ, giao dịch, tính nguyên tử, quyền truy cập hoặc sự kiện miền nghiệp vụ đã xác nhận.
- Muốn dùng cơ chế này an toàn, phải kiểm tra **phạm vi weaving, đường bypass, vòng lặp trong advice, đồng thời, dữ liệu nhạy cảm và chi phí đo đạc**.
- Khi điểm đọc/ghi không được công nghệ hỗ trợ, hãy dùng ranh giới phương thức hoặc một thiết kế tường minh phù hợp thay vì giả định hệ AOP tự động thấy mọi truy cập trạng thái.
