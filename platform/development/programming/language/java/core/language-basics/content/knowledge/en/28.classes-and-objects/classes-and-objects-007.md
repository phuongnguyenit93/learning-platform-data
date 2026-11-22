# Nhận diện `public`, `private` và truy cập trong gói trong Java

> **Java core — language-basics / Lớp và đối tượng**  
> **Môi trường:** JDK 17+, không dùng thư viện ngoài.  
> **Mục tiêu:** Đọc được modifier truy cập của lớp, constructor, trường và phương thức; phân biệt `public`, `private` và **package-private** (không viết modifier); sử dụng API công khai để bảo vệ trạng thái; biết khi nào mã cùng hoặc khác package được truy cập thành viên.

## 1. Ba mức truy cập cần nhận diện đầu tiên

Trong Java, *access modifier* quy định vị trí mã được phép sử dụng một lớp hoặc thành viên. Với các thành viên thông thường:

| Khai báo | Trong lớp khai báo | Lớp khác cùng package | Lớp không liên quan khác package |
| --- | --- | --- | --- |
| `public` | Có | Có | Có, nếu lớp khai báo cũng truy cập được |
| `private` | Có | Không | Không |
| **Không có modifier** (*package-private*) | Có | Có | Không |

Ví dụ nhận diện ba mức:

~~~java
class Sample {
    public int shown = 10;
    private int hidden = 20;
    int sharedWithinPackage = 30; // KHÔNG có access modifier.
}
~~~

- `public` cho phép sử dụng từ mã có quyền nhìn thấy lớp/kiểu chứa thành viên.
- `private` giữ thành viên trong phạm vi truy cập của lớp khai báo và những cấu trúc lồng nhau được ngôn ngữ cho phép; **một top-level class khác** dù cùng package không được đọc trực tiếp.
- Bỏ trống modifier được gọi là **package-private** hoặc *package access*: các lớp cùng package có thể truy cập, kể cả nằm ở file `.java` khác nhau.
- Không tồn tại từ khóa Java `package-private` hoặc `default` để viết trước khai báo; chỉ **bỏ trống** modifier.

Java còn có `protected`: mã cùng package được truy cập và lớp con ở package khác có quyền theo các quy tắc kế thừa đặc biệt. Bài này chỉ tập trung nhận diện ba trường hợp cơ bản; **không** hiểu `protected` đơn thuần là `public` cho mọi subclass trong mọi tình huống.

## 2. Package là gì, và không đồng nghĩa cùng một file

Một file Java có thể mở đầu bằng khai báo:

~~~java
package school.model;
~~~

Các lớp có cùng tên package như `school.model` được xem là cùng package dù nằm ở **nhiều file mã nguồn**. Ngược lại, hai lớp khác package không được phép dùng member package-private của nhau, dù chúng nằm gần nhau trong cấu trúc thư mục.

Java dùng dấu `.` để tách các phần trong tên package, nhưng tính cùng package dựa vào **tên package đầy đủ**, không phải tiền tố tên:

- `school.model` và `school.model`: cùng package.
- `school.model` và `school.app`: khác package.
- `school.model` và `school.model.extra`: **cũng khác package**; package con không tự kế thừa quyền package-private của package cha.

Một lớp không khai báo `package` thuộc **unnamed package** (thường gọi là *default package*) trong ví dụ nhập môn. Khi viết ứng dụng thật, nên dùng package có tên để tổ chức mã và tránh hạn chế khi tích hợp.

**Không trộn lẫn:** Cùng **project**, cùng **thư mục**, hoặc cùng **package cha** không mặc nhiên đồng nghĩa có quyền truy cập package-private. `import` cũng chỉ hỗ trợ tham chiếu theo tên; nó **không mở thêm quyền truy cập**.

## 3. Modifier trên lớp và trên thành viên là hai tầng khác nhau

Với **top-level class** (lớp không lồng trong lớp khác), hai mức cần nhớ:

~~~java
public class PublicType {
    // Được nhìn thấy bên ngoài package khi môi trường cho phép.
}

class PackageType {
    // Chỉ truy cập trực tiếp từ cùng package.
}
~~~

Khi viết thành file riêng, lớp top-level `public` phải nằm trong file có tên phù hợp, ví dụ `PublicType.java`. Một file nguồn thông thường không thể có hai lớp top-level `public` cùng được khai báo và biên dịch hợp lệ. Không dùng `private class Hidden { ... }` cho **top-level class**: modifier `private` không hợp lệ ở đây. Với **lớp lồng nhau** (`nested class`), `private` có thể hợp lệ.

Một member `public` nằm trong lớp top-level package-private **không biến lớp chứa nó thành public**:

~~~java
class PackageType {
    public void run() {
        System.out.println("running");
    }
}
~~~

Mã ở package khác vẫn không thể đặt tên và sử dụng `PackageType` trực tiếp chỉ vì `run()` được khai báo public. Muốn cung cấp API xuyên package, lớp/kiểu lộ ra cũng phải đủ mức truy cập, ngoài những điều kiện của module và ngữ cảnh biên dịch.

## 4. `private` giúp đóng gói trạng thái

Thông lệ nhập môn: giữ các trường có thể thay đổi ở `private`, rồi cung cấp phương thức công khai có kiểm tra điều kiện khi cần:

~~~java
class Wallet {
    private int balance;

    public Wallet(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("initial must be non-negative");
        }
        this.balance = initial;
    }

    public int balance() {
        return balance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    private boolean hasEnough(int amount) {
        return balance >= amount;
    }

    public boolean canPay(int amount) {
        return amount >= 0 && hasEnough(amount);
    }
}
~~~

`balance` và `hasEnough` là các thành viên private; mã ở lớp khác không thể gọi `wallet.hasEnough(...)` hay đọc `wallet.balance` trực tiếp. Phương thức `balance()`, `deposit(...)` và `canPay(...)` tạo API công khai và có thể gọi qua tham chiếu tới đối tượng `Wallet` tại nơi có quyền nhìn thấy `Wallet`.

**Lưu ý:** `private` là kiểm soát truy cập ở mức ngôn ngữ, không phải cơ chế mã hóa dữ liệu hoặc ranh giới bảo mật giữa các tiến trình. Đừng cho rằng một field private tự bảo vệ được mật khẩu hay dữ liệu nhạy cảm trước mọi hình thức quan sát.

## 5. Truy cập package-private: dùng có chủ đích

Nếu không viết modifier trên **trường**, **phương thức** hoặc **constructor**, mặc định đó là package-private:

~~~java
class Task {
    String phase = "NEW";             // Field package-private.

    Task() {                          // Constructor package-private.
    }

    void markStarted() {              // Method package-private.
        phase = "STARTED";
    }

    public String status() {          // Method public.
        return phase;
    }

    private void resetInternally() {  // Method private.
        phase = "NEW";
    }
}
~~~

Một lớp **khác trong cùng package** có thể gọi `new Task()`, đọc `task.phase`, gọi `task.markStarted()` và `task.status()`, nhưng không gọi `task.resetInternally()` vì private.

Package-private thường phù hợp cho mã **hỗ trợ nội bộ trong cùng package**. Tuy nhiên, gán trực tiếp trường package-private có thể bỏ qua kiểm tra bất biến trạng thái; không nên mở trường chỉ để “tiện” nếu getter/phương thức nghiệp vụ sẽ rõ ràng hơn.

Khai báo access modifier cho constructor độc lập với các phương thức khác: `public class Type` có thể có constructor private hoặc package-private. Vì vậy nhìn thấy **lớp public** chưa chắc đã gọi được `new Type()` từ mọi package.

## 6. Ví dụ một file: phân biệt public, private và trong gói

Chương trình sau cố ý chứa một lớp top-level `public` và hai lớp top-level **không ghi modifier**, nên cả ba lớp ở **cùng một package**. Nó minh họa lớp khác gọi được method/field package-private nhưng không đọc được field private.

Tạo file **AccessLevelsDemo.java**:

~~~java
public final class AccessLevelsDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 100, "A7");
        System.out.println("initial=" + account.summary());
        System.out.println("publicName=" + account.owner());
        System.out.println("packageField=" + account.category);
        System.out.println("packageMethod=" + account.internalCode());
        System.out.println("readerCode="
                + SamePackageReader.readCode(account));

        account.deposit(25);
        System.out.println("afterDeposit=" + account.balance());
        account.adjustInsidePackage(5);
        System.out.println("afterPackageAdjustment=" + account.balance());
        System.out.println("privateBridge="
                + account.privateInfoThroughClass());

        Account other = new Account("Bao", 40, "A7");
        System.out.println("sameInternalId="
                + account.sameInternalId(other));
        System.out.println("sameReference=" + (account == other));

        account.category = "VIP"; // Được phép vì cùng package.
        System.out.println("afterPackageField=" + account.summary());
        System.out.println("readerSummary="
                + SamePackageReader.readSummary(account));

        // KHÔNG BIÊN DỊCH nếu bỏ comment:
        // System.out.println(account.internalId); // private.
        // account.privateTag();                    // private.
    }
}

// Top-level class package-private: không ghi public/private.
final class Account {
    private final String name;
    private int balance;
    private final String internalId;
    String category = "BASIC"; // package-private field.

    Account(String name, int balance, String internalId) {
        this.name = name;
        this.balance = balance;
        this.internalId = internalId;
    }

    public String owner() {
        return name;
    }

    public int balance() {
        return balance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount > 0");
        }
        balance += amount;
    }

    String internalCode() { // package-private method.
        return name.substring(0, 1) + "-" + category;
    }

    void adjustInsidePackage(int delta) { // package-private.
        balance += delta;
    }

    private String privateTag() {
        return "tag:" + internalId;
    }

    String privateInfoThroughClass() {
        return privateTag(); // Chính lớp này được gọi private.
    }

    public boolean sameInternalId(Account other) {
        // Trong lớp Account có thể đọc private field
        // của một đối tượng Account KHÁC.
        return internalId.equals(other.internalId);
    }

    public String summary() {
        return name + ":" + balance + ":" + category;
    }
}

// Lớp thứ ba cùng package, truy cập được thành viên package-private.
final class SamePackageReader {
    static String readCode(Account account) {
        return account.internalCode();
    }

    static String readSummary(Account account) {
        return account.summary();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 AccessLevelsDemo.java
java AccessLevelsDemo
~~~

**Expected stdout chính xác:**

~~~text
initial=Lan:100:BASIC
publicName=Lan
packageField=BASIC
packageMethod=L-BASIC
readerCode=L-BASIC
afterDeposit=125
afterPackageAdjustment=130
privateBridge=tag:A7
sameInternalId=true
sameReference=false
afterPackageField=Lan:130:VIP
readerSummary=Lan:130:VIP
~~~

**Quan sát:** `SamePackageReader` gọi được `Account.internalCode()` vì các top-level classes nằm trong cùng package, dù là lớp khác. `internalId` và `privateTag()` vẫn không thể truy cập trực tiếp từ `AccessLevelsDemo` vì `private`. Bên trong chính `Account`, phương thức `sameInternalId` được đọc private field của **đối tượng `Account` khác**; private giới hạn mã truy cập theo lớp, **không** chỉ cho riêng `this`.

## 7. Qua hai package: điều gì còn truy cập được?

Khi đi sang package khác, điều kiện truy cập trở nên rõ hơn. Có thể thử hai file độc lập như sau.

**File `src/school/model/Student.java`:**

~~~java
package school.model;

public final class Student {
    private final int score = 8;
    String note = "class-only"; // package-private.

    public int score() {
        return score;
    }
}
~~~

**File `src/school/app/Main.java`:**

~~~java
package school.app;

import school.model.Student;

public final class Main {
    public static void main(String[] args) {
        Student student = new Student();
        System.out.println("outside=" + student.score());

        // KHÔNG BIÊN DỊCH nếu bỏ comment:
        // System.out.println(student.score); // private.
        // System.out.println(student.note);  // package-private.
    }
}
~~~

Biên dịch và chạy tại thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/school/model/Student.java src/school/app/Main.java
java -cp out school.app.Main
~~~

**Expected stdout:**

~~~text
outside=8
~~~

`import school.model.Student;` làm tên lớp dễ dùng hơn nhưng không cho phép truy cập `note` hoặc `score` trực tiếp. Gọi `student.score()` hợp lệ vì **cả lớp `Student` và phương thức `score()` đều public**. Nếu đổi `public final class Student` thành `final class Student`, class trở thành package-private và `Main` ở package khác không thể sử dụng kiểu này trực tiếp.

## 8. Phân biệt lỗi truy cập với các lỗi khác

| Tình huống | Nguyên nhân chính | Cách xử lý |
| --- | --- | --- |
| `account.internalId` từ top-level class khác | Field `private` | Dùng API hợp lệ hoặc đưa logic vào lớp sở hữu |
| `student.note` từ `school.app` | Field package-private, khác package | Cân nhắc public API; không lách quyền bằng `import` |
| `new HiddenType()` từ package khác | Top-level class package-private | Thiết kế kiểu public cần thiết hoặc giữ mã trong package |
| `new PublicType()` không hợp lệ vì constructor ẩn | Class public nhưng constructor không public | Dùng factory hợp lệ hoặc điều chỉnh API |
| `obj.method()` không truy cập được | Method private/package-private hoặc lớp khai báo không nhìn thấy | Kiểm tra cả class và method |
| `obj == null` rồi gọi instance method | `NullPointerException` lúc chạy; không phải access modifier | Tạo đối tượng/kiểm tra null |
| `private class X` ở cấp top-level | Modifier private không hợp lệ cho top-level class | Bỏ modifier hoặc biến thành nested class |
| `cannot find symbol` tên class | Có thể thiếu import, classpath hoặc tên | Kiểm tra tên/package trước khi kết luận lỗi access |

Một API nhỏ, rõ ràng thường dùng **field private** và **method public cần thiết**, còn package-private dành cho thành viên thực sự chỉ sử dụng nội bộ cùng package. Tránh đặt mọi field public chỉ để làm ví dụ chạy nhanh.

### Bài tập tự kiểm tra

1. Trong cùng package, tạo hai file `Book.java` và `BookDemo.java`. Cho `Book` có field package-private và field private; thử truy cập cả hai từ `BookDemo`.
2. Tách `BookDemo` sang package khác, thay `Book` thành `public class Book`. Những truy cập nào không còn biên dịch?
3. Định nghĩa class top-level không modifier nhưng có một phương thức public. Vì sao mã khác package vẫn không thể dùng class đó trực tiếp?
4. Viết constructor package-private và một static factory public trong lớp public. Khi nào mã khác package phải dùng factory?
5. Giải thích vì sao phương thức của `Account` có thể đọc `other.internalId` trong khi `SamePackageReader` không thể đọc cùng field.

### Ghi nhớ

**`public` mở truy cập theo API; `private` giữ thành viên trong phạm vi lớp/nested structure phù hợp; bỏ access modifier nghĩa là package-private — chỉ cùng package.** Quyền truy cập cần xét **cả kiểu khai báo và thành viên**. Cùng package không bắt buộc cùng file; package con vẫn là package khác; `import` không vượt qua access control. Hãy ưu tiên đóng gói trường private và cung cấp phương thức công khai có chủ đích.
