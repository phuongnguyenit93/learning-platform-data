# Quy tắc `protected` qua lớp con ở gói khác trong Java

Trong Java, **`protected`** có hai con đường truy cập cần phân biệt rõ: **truy cập từ code cùng package** với lớp khai báo, và **truy cập qua quan hệ kế thừa từ subclass thuộc package khác**. Con đường thứ hai có **quy tắc riêng về receiver** (đối tượng nằm trước dấu chấm) đối với **instance field** và **instance method**.

Đây là phần thường khiến người học ngạc nhiên:

~~~java
// Trong subclass S ở package khác với superclass C:
this.protectedMethod();    // Có thể hợp lệ
otherS.protectedMethod();  // Có thể hợp lệ nếu otherS có kiểu S
// otherC.protectedMethod(); // Thường lỗi nếu otherC có kiểu C
~~~

Dù `S extends C` và dù object `otherC` có thể trỏ tới một instance S ở runtime, Java vẫn kiểm tra **quyền truy cập dựa trên vị trí code và kiểu tĩnh của receiver**. Quan hệ kế thừa **không tự cấp phép cho subclass thao tác với protected state của mọi object thuộc superclass**.

Bài học này áp dụng cho **Java 17+**. Nội dung tập trung vào quy tắc `protected` qua lớp con ở package khác, đồng thời giải thích điều kiện nền tảng, các tình huống hợp lệ/sai, `super`, protected constructor, overriding, kiểu tham chiếu, generic, static members và các lưu ý thực hành.

## 1. Từ đâu phát sinh khác biệt giữa hai package?

Xét hai package:

~~~text
src/
├── library/
│   └── model/
│       └── Base.java
└── library/
    └── client/
        └── Derived.java
~~~

Một class thuộc package `library.model` **không cùng package** với một class thuộc `library.client`. Việc tên hai package cùng tiền tố `library` **không tạo quan hệ quyền truy cập đặc biệt**.

Trong Java, package được xác định bằng khai báo nguồn như:

~~~java
package library.model;
~~~

Hai tên package `library.model` và `library.model.internal` cũng **khác nhau**. Một subpackage theo tên gọi không kế thừa quyền truy cập package-private hoặc protected theo con đường same-package từ package cha.

Ví dụ:

~~~java
// File: src/library/model/Base.java
package library.model;

public class Base {
    protected int points = 10;

    protected String label() {
        return "Base";
    }
}
~~~

~~~java
// File: src/library/client/Derived.java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public String show() {
        return this.label() + ":" + this.points;
    }
}
~~~

Trong `Derived.show()`, `this.label()` và `this.points` đều được phép vì `Derived` là subclass của `Base` và quyền `protected` áp dụng theo quy tắc kế thừa tại ngữ cảnh phù hợp. Nhưng điều này **không có nghĩa** bất kỳ object `Base` nào truyền vào `Derived` cũng cho phép truy cập hai thành viên đó.

Hai tệp trên là **ví dụ khai báo riêng**, chưa có `main`. Một chương trình nhiều package hoàn chỉnh có stdout xác định sẽ được trình bày ở mục 5.

## 2. Nhớ đúng bản chất của `protected`

Trước khi tìm hiểu receiver rule, cần đặt `protected` bên cạnh các mức truy cập khác:

| Vị trí code truy cập member của class C | `public` | `protected` | Package-private | `private` |
| --- | :---: | :---: | :---: | :---: |
| Ngay trong C | Có | Có | Có | Có |
| Class khác cùng package C | Có | Có | Có | Không |
| Subclass S ở package khác | Có | Có điều kiện | Không | Không |
| Class khác package, không phải subclass | Có | Không | Không | Không |

**Protected không đồng nghĩa “chỉ lớp con”.** Khi class A và class B **cùng package**, B có thể truy cập protected member của A theo con đường same-package dù B không `extends A`. Ngược lại, khi B khác package, quyền protected đòi hỏi quan hệ subclass và điều kiện thêm.

**Package-private không đồng nghĩa protected.** Một member không viết modifier trong class thông thường là package-private; subclass ở package khác không được truy cập chỉ vì kế thừa.

**Private không mở cho subclass.** Subclass khác package cũng như subclass cùng package không được tự động đọc trực tiếp private field của superclass. Nếu superclass muốn cung cấp dữ liệu cho subclass, nó có thể định nghĩa một protected method (hoặc API public phù hợp), thay vì công khai field mutable.

Bài này giả sử **class khai báo member cũng truy cập được** từ vị trí code đang xét; nếu superclass là kiểu không truy cập được, phải kiểm tra thêm type accessibility. Với named modules, còn có những điều kiện export/readability ngoài bốn modifier cơ bản.

## 3. Quy tắc quan trọng nhất: kiểu receiver trong subclass khác package

Giả sử:

- `C` là superclass **khai báo** một protected instance field hoặc instance method.
- `S extends C` là subclass nằm ở **package khác**.
- Code dùng protected member nằm trong **ngữ cảnh subclass `S`** đủ điều kiện theo Java Language Specification (JLS `6.6.2).
- Một biểu thức `receiver.member` sử dụng member được khai báo trong C.

Khi truy cập protected **instance** member qua một biểu thức receiver, Java yêu cầu kiểu **compile-time** của biểu thức receiver phải là **`S` hoặc một subclass của `S`** theo các quy tắc tương ứng.

Ví dụ:

~~~java
// Đoạn code nằm trong S extends C,
// S và C thuộc hai package khác nhau.
void example(S sameType, C baseType) {
    this.protectedMethod();      // Hợp lệ
    sameType.protectedMethod();  // Hợp lệ

    // baseType.protectedMethod(); // Lỗi compile
}
~~~

Ở dòng `sameType.protectedMethod()`, parameter khai báo kiểu `S`, thỏa giới hạn receiver. Với `baseType`, compiler nhìn thấy kiểu `C` — **rộng hơn `S`** — nên việc truy cập instance protected member bị từ chối trong ngữ cảnh khác package.

**Không phải compiler đang đoán object nào thật sự được truyền vào.** Nó kiểm tra dựa trên **kiểu được suy ra/khai báo tại thời điểm biên dịch**. Một biến `C baseType` có thể nhận object runtime thuộc `S`, nhưng biểu thức `baseType.protectedMethod()` vẫn không tự hợp lệ chỉ vì runtime object là S.

### 3.1. Phân biệt quyền của ngữ cảnh và kiểu receiver

Quyền truy cập protected khác package cần xem **hai câu hỏi độc lập**:

1. **Đoạn code đang nằm ở đâu?** Có thực sự thuộc một ngữ cảnh subclass S có quyền truy cập member khai báo trong C không?
2. **Nếu dùng một receiver expression cho instance member, kiểu của receiver là gì?** Có phải S hoặc subtype của S theo quy tắc protected access không?

Nếu chỉ thỏa một trong hai, lời gọi vẫn có thể bị từ chối.

Ví dụ một class `Viewer` ở cùng package với S nhưng **không phải subclass** của C không được phép tùy ý truy cập protected instance field **khai báo trong C** chỉ bằng cách có một biến kiểu S.

### 3.2. Cùng package C thì không áp dụng hạn chế receiver kiểu subclass này

Trong class thuộc **cùng package với C**, protected instance member có thể được truy cập qua một biến kiểu `C` theo con đường same-package:

~~~java
// File: model/Peer.java; cùng package model với C
class Peer {
    int read(C object) {
        return object.protectedField;
    }
}
~~~

Đây là ví dụ về nguyên tắc, cần có class C tương ứng. `Peer` không phải subclass vẫn có quyền do **cùng package**. Vì vậy, đừng áp dụng công thức “receiver phải kiểu S” cho mọi protected access: công thức đó dành cho trường hợp **subclass khác package** khi truy cập protected **instance** member qua receiver.

## 4. `this`, `super`, tham số kiểu S và tham số kiểu C

Xét `Derived extends Base` ở package khác:

~~~java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public int readSelf() {
        return this.points;       // Hợp lệ
    }

    public int readSuperclassView() {
        return super.points;      // Hợp lệ
    }

    public int readPeer(Derived other) {
        return other.points;      // Hợp lệ: kiểu receiver là Derived
    }

    public int readBase(Base other) {
        // return other.points;   // Lỗi: kiểu receiver là Base
        return other.publicPoints();
    }
}
~~~

Đoạn này giả sử `Base` có một method `public int publicPoints()`. Nó là **minh họa điều kiện truy cập**; chương trình hoàn chỉnh bên dưới cung cấp source đầy đủ.

Giải thích:

- `this.points`: dùng current subclass object; hợp lệ.
- `super.points`: truy cập member của superclass trên current object bằng cú pháp `super`; hợp lệ theo quy tắc truy cập/lookup liên quan.
- `other.points` khi other là `Derived`: hợp lệ theo giới hạn receiver.
- `other.points` khi other là `Base`: không hợp lệ ở subclass khác package vì kiểu tĩnh quá rộng.
- `other.publicPoints()`: hợp lệ vì public API của Base, nếu class và method đều accessible.

**`super` không trỏ tới một object Base riêng.** Khi object thực tế là Derived, các field kế thừa thuộc object đó; `super` là cách truy cập thành viên superclass theo cơ chế của ngôn ngữ.

### 4.1. Kiểu runtime khác kiểu compile-time

~~~java
Base base = new Derived();

// Trong Derived method, base.points vẫn bị từ chối
// nếu receiver expression có kiểu compile-time Base.
~~~

Runtime object là Derived nhưng biến `base` có compile-time type Base. Cách compiler chọn một member và xác minh accessibility dựa trên kiểu biểu thức và ngữ cảnh nguồn; runtime dispatch không xóa quyền hạn đã được kiểm tra tại compile time.

Đây là một nguyên tắc rất hữu ích cả ở ngoài chủ đề protected: **kiểu static quyết định những thao tác nào được compiler cho phép**, còn runtime class có thể quyết định implementation nào chạy cho một instance method được override.

## 5. Chương trình nhiều package chạy được: đủ các trường hợp then chốt

Ví dụ này có bốn tệp trong hai package. Nó chứng minh:

- Code cùng package của superclass đọc được protected member qua `Base`.
- Subclass ở package khác đọc protected member qua `this`, `super` và receiver kiểu subclass.
- Subclass **không** được đọc qua parameter khai báo kiểu superclass.
- Code bên ngoài **không** được đọc protected member gốc chỉ bằng một reference object.
- Static protected method có thể được subclass dùng trong ngữ cảnh phù hợp.
- Protected instance method override vẫn chịu **dynamic dispatch**.

### 5.1. Cấu trúc thư mục

~~~text
src/
├── library/
│   └── model/
│       ├── Base.java
│       └── Peer.java
└── library/
    └── client/
        ├── Derived.java
        └── Demo.java
~~~

### 5.2. Tệp `src/library/model/Base.java`

~~~java
package library.model;

public class Base {
    protected final String id;

    protected Base(String id) {
        this.id = id;
    }

    protected String label() {
        return "Base";
    }

    protected static String code() {
        return "STATIC";
    }

    public String description() {
        return "Base#" + id;
    }
}
~~~

Class `Base` là public để subclass ở package khác có thể `extends Base`. Constructor `Base(String)` là protected; subclass ngoài package có thể gọi nó bằng `super(id)`. Field `id` là protected instance member; method `label()` là protected instance method; method `code()` là protected static method. `description()` là public API.

### 5.3. Tệp `src/library/model/Peer.java`

~~~java
package library.model;

public class Peer {
    public static Base create(String id) {
        return new Base(id);
    }

    public static String inspect(Base object) {
        return object.label() + "/" + object.id;
    }
}
~~~

`Peer` không kế thừa Base nhưng **cùng package `library.model`**. Do đó, `new Base(id)` có thể gọi protected constructor và `object.label()`, `object.id` hợp lệ ngay cả khi receiver kiểu Base.

### 5.4. Tệp `src/library/client/Derived.java`

~~~java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public Derived(String id) {
        super(id);
    }

    @Override
    protected String label() {
        return "Derived";
    }

    public String fromThis() {
        return this.label() + "/" + this.id;
    }

    public String fromSuper() {
        return super.label() + "/" + super.id;
    }

    public String fromPeer(Derived other) {
        return other.label() + "/" + other.id;
    }

    public String fromBase(Base other) {
        // return other.label() + "/" + other.id;
        // Sai: receiver của member protected khai báo trong Base
        // có compile-time type Base, không phải Derived.
        return other.description();
    }

    public static String staticInfo() {
        return code();
    }
}
~~~

Các dòng không hợp lệ được comment để chương trình chạy được. `@Override protected String label()` giữ mức protected và thay implementation ở subclass; điều đó được phép vì không thu hẹp access. Code trong Derived được gọi các protected members thông qua `this`, `super` hoặc receiver kiểu Derived.

### 5.5. Tệp `src/library/client/Demo.java`

~~~java
package library.client;

import library.model.Base;
import library.model.Peer;

public class Demo {
    public static void main(String[] args) {
        Derived first = new Derived("A");
        Derived second = new Derived("B");
        Base base = Peer.create("X");

        System.out.println("This = " + first.fromThis());
        System.out.println("Peer = " + first.fromPeer(second));
        System.out.println("Super = " + first.fromSuper());
        System.out.println("Base = " + first.fromBase(base));
        System.out.println("Same package = " + Peer.inspect(base));
        System.out.println("Dynamic dispatch = " + Peer.inspect(first));
        System.out.println("Static = " + Derived.staticInfo());
        System.out.println("Public = " + first.description());

        // System.out.println(first.id);    // Không hợp lệ ở Demo
        // System.out.println(base.label()); // Không hợp lệ ở Demo
        // new Base("T");                    // Không hợp lệ ở Demo
    }
}
~~~

`Demo` cùng package với **Derived** nhưng **khác package Base** và không phải subclass Base. Nó không tự được cấp quyền đối với **field `id` khai báo trong Base** chỉ vì biến `first` có kiểu Derived. `Demo` có thể gọi public methods của Derived để yêu cầu Derived sử dụng protected member một cách hợp lệ từ chính subclass.

Một chi tiết nâng cao: `Derived.label()` là một **khai báo override protected mới trong package `library.client`**, vì vậy code cùng package với `Derived` có thể truy cập method được khai báo tại Derived theo con đường same-package. Nhưng điều đó **không chuyển field `Base.id` sang package client**, cũng không khiến protected member **khai báo trong Base** bỗng là package-private đối với mọi class ở client.

### 5.6. Biên dịch và chạy với JDK 17+

Đứng ở thư mục chứa `src`:

~~~bash
javac -encoding UTF-8 -d out src/library/model/Base.java src/library/model/Peer.java src/library/client/Derived.java src/library/client/Demo.java
java -cp out library.client.Demo
~~~

**Stdout chính xác:**

~~~text
This = Derived/A
Peer = Derived/B
Super = Base/A
Base = Base#X
Same package = Base/X
Dynamic dispatch = Derived/A
Static = STATIC
Public = Base#A
~~~

Diễn giải kết quả:

1. `first.fromThis()` gọi `this.label()` (Derived) và đọc `this.id` (field được khai báo ở Base), nên trả `Derived/A`.
2. `first.fromPeer(second)` có parameter kiểu Derived, được gọi protected member trên object Derived khác, nên `Derived/B`.
3. `first.fromSuper()` dùng `super.label()` để chọn implementation Base, còn `super.id` đọc field Base của current object, nên `Base/A`.
4. `first.fromBase(base)` không cố đọc protected member qua `Base` parameter mà dùng public `description()`, trả `Base#X`.
5. `Peer.inspect(base)` nằm trong package Base, nên dùng protected `label()` và `id` trên receiver kiểu Base hợp lệ; kết quả `Base/X`.
6. `Peer.inspect(first)` vẫn được phép truy cập theo same-package của nơi method `Peer.inspect` khai báo. Lời gọi `object.label()` **dynamic dispatch** tới override trong Derived, nên kết quả `Derived/A`.
7. `Derived.staticInfo()` gọi protected static method kế thừa `code()` trong ngữ cảnh subclass phù hợp, trả `STATIC`.
8. `first.description()` là public method kế thừa từ Base, trả `Base#A`.

**Các lỗi quyền truy cập để thử:** bỏ comment **từng dòng** có dấu `//` ở `Derived.fromBase` hoặc `Demo.main`, chạy lại `javac`, quan sát compiler từ chối. Đừng bỏ comment mọi dòng đồng thời nếu muốn gắn lỗi với chính xác một quy tắc.

## 6. Vì sao `otherDerived.protected` hợp lệ nhưng `otherBase.protected` không?

Xét trong code của subclass S ở package khác:

~~~java
S sameBranch = new S();
C broadType = sameBranch;

sameBranch.protectedField; // Được nếu đáp ứng điều kiện khác
// broadType.protectedField; // Bị từ chối: kiểu tĩnh C
~~~

Dù **hai biến có thể cùng trỏ tới một object**, quyền truy cập instance protected member được kiểm tra **theo kiểu của biểu thức receiver** trong ngữ cảnh subclass S.

Đây không phải cơ chế bảo mật runtime xác minh riêng từng object. Nó là **ràng buộc ở mức ngôn ngữ nguồn**, hạn chế cách một subclass ở package khác dùng protected state của superclass.

### 6.1. “Bất kỳ subclass nào cũng gọi được” là diễn đạt quá rộng

Giả sử:

~~~text
Base
├── Alpha (package x)
└── Beta  (package y)
~~~

`Alpha` và `Beta` đều extends Base, nhưng `Beta` **không phải subtype của Alpha**. Trong method của Alpha, lời gọi `beta.protectedField` qua biến khai báo kiểu Beta thường **không hợp lệ** theo quy tắc protected instance receiver nếu package Beta/Alpha khác package khai báo member ở Base.

Ví dụ:

~~~java
package app.alpha;

import api.Base;
import app.beta.Beta;

public class Alpha extends Base {
    public int inspect(Beta beta) {
        // return beta.protectedValue; // Sai: Beta không là subtype của Alpha
        return 0;
    }
}
~~~

Đây là đoạn minh họa; cần các class `api.Base` và `app.beta.Beta` tương ứng. Hai nhánh con **cùng có quyền truy cập thành viên protected từ chính ngữ cảnh của mình**, nhưng không có quyền chạm protected instance member trên object của một nhánh subclass không tương thích.

### 6.2. Một subclass của S thì sao?

Nếu `SportDerived extends Derived` và code nằm trong `Derived`, thì `SportDerived` là subtype của Derived. Với một receiver được khai báo kiểu `SportDerived`, điều kiện kiểu receiver `Derived hoặc subtype` có thể được đáp ứng khi truy cập protected member của Base trong ngữ cảnh Derived.

Nói cách khác, **subclass khác package được phép thao tác qua nhánh kế thừa của chính subclass đó**, chứ không được truy cập mọi object mang type C hoặc một nhánh anh em.

## 7. Upcast, downcast, `instanceof`: điều gì thay đổi, điều gì không?

**Upcast** một subclass reference sang superclass type khiến quyền được compiler nhìn thấy qua reference có thể hẹp đi ở vị trí gọi:

~~~java
Derived derived = new Derived("A");
Base upcast = derived;
~~~

Trong một method của Derived thuộc package khác Base:

~~~java
void check(Base upcast, Derived direct) {
    direct.label(); // Hợp lệ
    // upcast.label(); // Lỗi do kiểu receiver Base
}
~~~

Dù `upcast` có thể đang trỏ tới đúng object mà `direct` trỏ tới, compile-time type của `upcast` vẫn là Base.

### 7.1. Ép kiểu có thể thay đổi kiểu tĩnh của biểu thức nhưng không cấp quyền cho mọi code

Từ ngữ cảnh subclass được phép, nếu muốn xử lý một parameter Base mà **chỉ khi nó thực sự là Derived**, có thể dùng pattern matching `instanceof` (Java 17):

~~~java
package library.client;

import library.model.Base;

public class TypeCheckedDerived extends Base {
    public TypeCheckedDerived(String id) {
        super(id);
    }

    public static String inspect(Base candidate) {
        if (candidate instanceof TypeCheckedDerived derived) {
            return derived.id; // Hợp lệ trong ngữ cảnh subclass này
        }
        return "Không phải TypeCheckedDerived";
    }
}
~~~

Đây là class minh họa riêng cần `library.model.Base` ở phần trước. Pattern variable `derived` có kiểu `TypeCheckedDerived`, nên thỏa điều kiện receiver khi truy cập field protected `Base.id` từ chính subclass `TypeCheckedDerived`. Nếu `candidate` không thuộc runtime type đó, nhánh không chạy.

**Ép kiểu không phá access control:** đoạn code trong một class ngoài package **không phải subclass đủ điều kiện** không tự có quyền đọc `Base.id` chỉ bằng cách cast receiver thành Derived. Đồng thời, cast không làm một Base object bất kỳ thật sự trở thành Derived: ép kiểu sai có thể gây `ClassCastException`.

### 7.2. Dynamic dispatch không thay thế kiểm tra truy cập

Một method instance được override có thể chạy ở subclass theo runtime type, nhưng **lời gọi vẫn phải hợp lệ về quyền truy cập** theo compile-time type/ngữ cảnh của caller.

Ví dụ `Peer.inspect(first)` trong chương trình chính là hợp lệ vì code của Peer nằm cùng package với Base. Sau khi lời gọi hợp lệ, `label()` trên object Derived dispatch đến implementation override. Trường hợp `upcast.label()` viết trực tiếp trong subclass package khác lại có thể **không biên dịch**, dù runtime object cũng là Derived.

**Hai bước khác nhau:**

1. **Compile time:** tìm member, chọn overload và xác minh quyền truy cập theo quy tắc Java.
2. **Runtime:** với instance method overridable, tìm implementation phù hợp của object thật.

## 8. `super.method()` và protected member trên current object

Trong subclass, `super.method()` chọn implementation phù hợp từ superclass theo quy tắc gọi `super`. Đây không phải lời gọi trên một object Base mới.

~~~java
class BaseCounter {
    protected int current() {
        return 1;
    }
}

class AdvancedCounter extends BaseCounter {
    @Override
    protected int current() {
        return 2;
    }

    int both() {
        return this.current() + super.current();
    }
}
~~~

`new AdvancedCounter().both()` trả `3`. `this.current()` chọn override trả 2, `super.current()` chọn superclass implementation trả 1. Đây là đoạn khai báo trong cùng package để minh họa cơ chế chọn implementation; quan hệ giữa `this` và `super` cũng áp dụng trong subclass khác package khi quyền protected hợp lệ.

**Không thể viết `someOtherObject.super.method()`** như cách tự do dùng một receiver của superclass bất kỳ. Cú pháp `super` có ngữ cảnh và ý nghĩa chuyên biệt, không phải một phép toán làm “mở khóa” protected member của mọi object.

## 9. Protected constructor ở package khác

Protected constructor khác protected instance field/method ở điểm **không có đối tượng đang tồn tại để bạn dùng receiver tùy ý**. Nó phục vụ kiểm soát những con đường khởi tạo:

~~~java
// File: src/api/Task.java
package api;

public class Task {
    private final String name;

    protected Task(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

~~~java
// File: src/app/CustomTask.java
package app;

import api.Task;

public class CustomTask extends Task {
    public CustomTask() {
        super("custom");       // Hợp lệ: subclass constructor
    }

    public static void demo() {
        // new Task("other");  // Không hợp lệ ở đây
    }
}
~~~

`CustomTask` thuộc package khác `Task` nhưng kế thừa Task, nên constructor của nó có thể gọi `super("custom")` đến protected superclass constructor. Tuy nhiên, một method của subclass **không được dùng `new Task("other")` như thể protected constructor là public**.

Quy tắc của JLS `6.6.2.2` cũng nêu những trường hợp đặc thù liên quan **anonymous class instance creation** sử dụng protected constructor; không nên suy luận đơn giản rằng protected constructor **chỉ** có thể được gọi trong mọi trường hợp thông qua `super(...)`. Nhưng đối với **subclass thông thường ở package khác**, `super(...)` là cơ chế quan trọng nhất cần thành thạo.

### 9.1. Không lẫn với `this(...)`

Trong subclass constructor:

~~~java
public CustomTask() {
    super("custom");
}
~~~

`super(...)` gọi constructor superclass. Còn `this(...)` — khi đặt ở đầu constructor theo Java 17 — ủy quyền tới **constructor khác cùng class**. Cả hai chịu quy tắc constructor invocation, khác với `this.protectedMethod()`.

## 10. `protected` static member: không áp dụng máy móc quy tắc receiver instance

Giới hạn `receiver là S hoặc subtype của S` ở trên nhắm đến **protected instance fields/methods**. Static members thuộc lớp về mặt khai báo, không thực thi trên một instance cụ thể.

Ví dụ:

~~~java
// File: api/BaseConfig.java
package api;

public class BaseConfig {
    protected static String category() {
        return "BASE";
    }
}
~~~

~~~java
// File: client/ClientConfig.java
package client;

import api.BaseConfig;

public class ClientConfig extends BaseConfig {
    public static String readCategory() {
        return category(); // Hợp lệ trong subclass
    }
}
~~~

Hai đoạn khai báo thuộc các file khác nhau. `ClientConfig.readCategory()` là public static wrapper để bên ngoài gọi qua API rõ ràng, còn `category()` được sử dụng từ ngữ cảnh subclass hợp lệ.

Nên gọi static members bằng tên class phù hợp hoặc cách không định danh khi có lý do, tránh gọi static qua object tham chiếu rồi nhầm đó là instance dispatch. **Không dùng bảng receiver của instance để suy đoán tất cả cú pháp truy cập static protected**, vì chúng có quy tắc truy cập/lookup riêng.

## 11. Override protected method khi subclass ở package khác

Subclass khác package có thể override một **protected instance method** kế thừa được, với điều kiện thỏa các quy tắc overriding, trong đó **không được thu hẹp mức truy cập**.

~~~java
// Trong package api:
public class Parent {
    protected String format() {
        return "parent";
    }
}
~~~

~~~java
// Trong package client:
public class Child extends Parent {
    @Override
    protected String format() {
        return "child";
    }
}
~~~

Các khai báo này cần nằm trong file/package tương ứng. `Child.format()` giữ protected, nên hợp lệ. Nếu đổi thành `public String format()` cũng **mở rộng visibility** và hợp lệ. Nếu đổi thành `private String format()`, compiler từ chối vì giảm visibility.

### 11.1. Override thành public và kiểu khai báo ở caller

Đây là một tình huống nâng cao rất đáng nhớ. Tạo ba tệp:

~~~text
src/
├── api/
│   └── Node.java
└── client/
    ├── NamedNode.java
    └── UseNode.java
~~~

**`src/api/Node.java`:**

~~~java
package api;

public class Node {
    protected String tag() {
        return "node";
    }

    public String describe() {
        return tag();
    }
}
~~~

**`src/client/NamedNode.java`:**

~~~java
package client;

import api.Node;

public class NamedNode extends Node {
    @Override
    public String tag() {
        return "named";
    }
}
~~~

**`src/client/UseNode.java`:**

~~~java
package client;

import api.Node;

public class UseNode {
    public static void main(String[] args) {
        NamedNode child = new NamedNode();
        Node widened = child;

        System.out.println("Child = " + child.tag());
        System.out.println("Via public = " + widened.describe());
        System.out.println("Via cast = " + ((NamedNode) widened).tag());

        // widened.tag(); // Lỗi compile: Node.tag() là protected
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 -d out src/api/Node.java src/client/NamedNode.java src/client/UseNode.java
java -cp out client.UseNode
~~~

Stdout:

~~~text
Child = named
Via public = named
Via cast = named
~~~

**Giải thích chi tiết:**

- `NamedNode.tag()` được khai báo **public** trong NamedNode, nên `child.tag()` là lời gọi hợp lệ ở client.
- `widened` có **compile-time type `Node`**, trong đó method `tag()` được khai báo **protected** ở package `api`. Vì `UseNode` không phải subclass đủ điều kiện và không cùng package api, `widened.tag()` **không hợp lệ**, dù object thật là NamedNode có override public.
- `widened.describe()` hợp lệ vì `Node.describe()` public. Bên trong `describe()`, lời gọi `tag()` dynamic dispatch tới NamedNode, nên kết quả là `named`.
- `((NamedNode) widened).tag()` có receiver compile-time type `NamedNode` với method public, đồng thời object runtime thật là NamedNode nên cast an toàn. Đây không phải cách **vượt** protected rule; nó gọi **một public method của kiểu subclass**.

Chốt lại: **một public override không tự làm cho method protected trong superclass trở thành public khi truy cập qua reference khai báo kiểu superclass**.

## 12. Hai subclass “anh em” ở các package khác nhau

Xét:

~~~text
api.Base
   |
   +--- client.a.Alpha
   |
   +--- client.b.Beta
~~~

`Alpha` và `Beta` cùng kế thừa Base nhưng **không subclass của nhau**. Trong method của Alpha, một parameter kiểu Beta thường **không thỏa protected receiver rule của Alpha** khi truy cập protected instance member khai báo trong Base.

~~~java
// File: client/a/Alpha.java
package client.a;

import api.Base;
import client.b.Beta;

public class Alpha extends Base {
    public String read(Beta beta) {
        // return beta.protectedText(); // Lỗi: Beta không là Alpha/subtype
        return "Không được truy cập trực tiếp";
    }
}
~~~

Đây là đoạn minh họa cần các kiểu `api.Base` và `client.b.Beta` phù hợp; không phải chương trình chạy độc lập. Dù Alpha có quyền đọc protectedText qua `this` của mình, nó **không có quyền tương đương đối với mọi instance Beta**.

Nếu Beta cung cấp một **public method** diễn đạt dữ liệu được phép công khai, Alpha có thể gọi method public đó. Đây thường là thiết kế tốt hơn việc hai sibling subclasses cố đọc protected state của nhau.

## 13. Class ngoài package có thể gọi public wrapper, không trực tiếp “mượn” quyền subclass

Một method public trong subclass có thể gọi protected helper trong superclass từ ngữ cảnh hợp lệ rồi trả dữ liệu cho caller:

~~~java
// Trong subclass hợp lệ:
public String formattedLabel() {
    return this.protectedLabel();
}
~~~

Caller khác package, không phải subclass, có thể viết `subclass.formattedLabel()` nếu method public và class accessible. Điều đó **không có nghĩa caller tự được quyền gọi `subclass.protectedLabel()`** khi member protected được khai báo tại package khác và không có con đường truy cập tương ứng.

Cách thiết kế này tách quyền:

- **Superclass** công bố extension point cho subclass bằng protected API.
- **Subclass** chủ động sử dụng extension point đó trong implementation hợp lệ.
- **Caller ngoài** chỉ được nhìn thấy public API mà subclass hoặc superclass lựa chọn mở.

Một public wrapper không phải thủ thuật compiler: nó là **hợp đồng API mới do người thiết kế class công khai**. Nếu wrapper làm lộ dữ liệu nhạy cảm, cần xem xét lại thiết kế bất kể Java cho phép biên dịch.

## 14. Quy tắc với protected field khác gì protected method?

Về **phạm vi truy cập từ subclass khác package**, protected instance field và protected instance method đều chịu quy tắc receiver quan trọng đã nêu. Nhưng **hành vi runtime** khác nhau:

- Truy cập field như `other.value` không có dynamic dispatch kiểu override method. Field hiding trong subclass không làm một field access tự chọn field theo runtime type giống virtual method.
- Gọi instance method `other.readValue()` có thể dynamic dispatch tới implementation override **sau khi** lời gọi được compiler chấp thuận.
- `super.value` và `this.value` có thể khác nếu subclass khai báo một field cùng tên; việc **hiding field** thường làm code khó hiểu nên nên tránh.
- `super.readValue()` và `this.readValue()` có thể chọn implementation khác nhau khi method override.

Ví dụ minh họa cùng package để tập trung vào field versus method:

~~~java
class Parent {
    protected String name = "field-parent";

    protected String name() {
        return "method-parent";
    }
}

class Child extends Parent {
    protected String name = "field-child";

    @Override
    protected String name() {
        return "method-child";
    }

    String explain() {
        return this.name + "/"
                + super.name + "/"
                + this.name() + "/"
                + super.name();
    }
}
~~~

`new Child().explain()` trả `field-child/field-parent/method-child/method-parent`. Đây là đoạn khai báo, không có `main`. Trong dự án thật, nên tránh dùng tên field và method gây nhầm hoặc che field superclass trừ khi có lý do đặc biệt.

## 15. `protected` không có nghĩa object con được kiểm soát tất cả state cha

Một superclass có thể dùng protected để cung cấp một phần API mở rộng cho subclass. Nhưng nó vẫn cần bảo vệ **class invariants**:

~~~java
public class BankAccount {
    private long balance;

    public BankAccount(long opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = opening;
    }

    protected final long currentBalance() {
        return balance;
    }

    protected final void addBalance(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }

    public long balance() {
        return balance;
    }
}
~~~

Lưu ví dụ độc lập class này thành `BankAccount.java` nếu muốn biên dịch. Ở đây:

- `balance` là **private**, không thể bị subclass tự ý viết `balance = -999`.
- `currentBalance()` và `addBalance(...)` protected tạo **các extension operations có kiểm soát**.
- `final` trên method bảo đảm subclass không override và phá validation của chính các operation này; tuy nhiên nó không tự bảo vệ mọi trường hợp concurrency.
- Subclass ở package khác vẫn cần tuân thủ quy tắc protected access: gọi `this.addBalance(...)` hợp lệ trong ngữ cảnh phù hợp, không có quyền gọi trên bất kỳ BankAccount object nào mà nó nhìn thấy.

**Ưu tiên protected method có hợp đồng hơn protected mutable field.** Một field protected làm subclass phụ thuộc chặt vào cấu trúc internal state và dễ phá invariant. `protected` là công cụ hỗ trợ mở rộng hành vi, không phải lý do để publicize gần như toàn bộ state cho mọi subclass.

## 16. Quy tắc truy cập protected có áp dụng mọi class như nhau không?

### 16.1. Top-level class không được khai báo `protected`

~~~java
// Sai nếu viết ở top level:
// protected class Helper { }
~~~

Top-level class hoặc interface thông thường chỉ có thể `public` hoặc package-private về access. `protected` có thể áp dụng cho **member type** ở những ngữ cảnh được phép, nhưng không áp dụng như access modifier cho một top-level class.

### 16.2. Interface không khai báo protected instance method theo kiểu class

Abstract interface methods trong Java thường được ngầm hiểu là `public abstract` nếu không ghi modifiers thích hợp. Không dùng `protected void act();` trong interface để làm extension point như trong class. Nếu cần protected implementation detail, có thể cân nhắc một abstract class hoặc thiết kế API khác.

### 16.3. Nested class và protected member type có quy tắc riêng

Một class có thể định nghĩa protected nested type:

~~~java
public class Outer {
    protected static class Helper {
        protected Helper() {
        }
    }
}
~~~

Đây là khai báo hợp lệ trong file `Outer.java`. Khả năng dùng tên `Helper`, tạo instance Helper từ package khác và truy cập constructor vẫn chịu các quy tắc access phù hợp, không đơn giản là “subclass thấy `Helper` thì ai cũng được `new Helper()`”.

Điểm học trọng tâm của bài này vẫn là **protected instance field/method qua subclass ở package khác**; không áp dụng máy móc chính xác cùng một kiểm tra receiver cho mọi trường hợp constructor, static và nested types.

## 17. Java modules có thể giới hạn thêm khả năng dùng public superclass

Nếu chương trình sử dụng **named modules** (Java 9+), class `api.Base` public ở một package không được export ra module khác có thể không được code client sử dụng như trong classpath demo.

Ví dụ trong `module-info.java` của module khai báo Base:

~~~java
module example.model {
    exports api;
}
~~~

Và trong client module:

~~~java
module example.client {
    requires example.model;
}
~~~

Đây là **đoạn khai báo module riêng biệt**, không phải hai declaration trong cùng tệp. Việc `exports api` và `requires example.model` giúp tạo điều kiện module readability/accessibility theo JPMS, nhưng **không làm mất quy tắc protected receiver**.

Cần kiểm tra theo thứ tự:

1. Module client có đọc được module chứa superclass không?
2. Package/type khai báo superclass có accessible không?
3. Member có mức truy cập phù hợp không?
4. Nếu là protected instance member qua subclass ở package khác, receiver type có thỏa `S hoặc subtype S` không?

**Module access và protected access là hai lớp điều kiện, không thay thế nhau.** Ví dụ nhiều package ở mục 5 chạy trên classpath để người mới học quan sát đúng quy tắc source-level mà không phải cấu hình module.

## 18. Những lỗi thường gặp

| Sai lầm | Điều đúng |
| --- | --- |
| Nghĩ `protected` chỉ truy cập được trong subclass | Class khác **cùng package** cũng truy cập được protected member |
| Nghĩ subclass ở package khác truy cập được protected member trên mọi object C | Với instance member cần kiểm tra receiver type S hoặc subtype S |
| Nghĩ package `a.b.c` thuộc “cùng package” với `a.b` | Chúng là hai package khác nhau |
| Dựa vào runtime type S của một biến khai báo C để gọi protected | Quyền access được kiểm tra theo compile-time type/ngữ cảnh |
| Nghĩ `import C` làm protected member thành public | Import không mở visibility |
| Nghĩ `super.member` tạo Base object mới | `super` chọn member superclass trên current object |
| Nghĩ mọi subclass anh em có thể đọc protected fields của nhau | Không nếu receiver không thỏa type rule của subclass nơi code truy cập |
| Nghĩ `protected Base(...)` cho phép `new Base(...)` ở mọi method subclass khác package | Protected constructor có quy tắc invocation riêng |
| Nghĩ `protected static` có cùng instance receiver rule | Static member không phải instance member; cần xét quy tắc riêng |
| Nghĩ override public khiến access qua Base reference tự public | Compile-time member lookup/access vẫn theo kiểu receiver/khai báo |
| Nghĩ `private` field có thể đọc trực tiếp từ subclass | Private member không mở bởi `extends` |
| Nghĩ `protected` field bảo vệ invariant tốt như method | Subclass có thể sửa field, dễ tạo state không hợp lệ |
| Nghĩ access check và dynamic dispatch là một việc | Compile kiểm tra quyền, runtime chọn override sau khi lời gọi hợp lệ |
| Nghĩ `protected` trên top-level class hợp lệ | Top-level class không dùng protected |

## 19. Bài tập tự kiểm tra

**Câu 1.** Class `A` và `B` ở cùng package; `A` có `protected int x`. `B` không kế thừa A. `B` có thể đọc `a.x` trên receiver kiểu A không?

**Đáp án:** Có, nếu các điều kiện khác thỏa mãn. Same-package access cho phép, không đòi B extends A.

**Câu 2.** `S extends C` thuộc package khác; method của S viết `this.protectedField`. Có hợp lệ không?

**Đáp án:** Có khi member thực sự là protected và ngữ cảnh subclass/truy cập đúng; `this` là current S instance.

**Câu 3.** Trong cùng method của S, `C c` là parameter; viết `c.protectedField` có hợp lệ như `this.protectedField` không?

**Đáp án:** Không. Nếu protected instance member được khai báo trong C ở package khác, receiver type `C` không thỏa giới hạn cần là `S hoặc subtype S`.

**Câu 4.** Thay khai báo parameter `C c` thành `S c` có thay đổi điều kiện truy cập không?

**Đáp án:** Có. Compile-time receiver type trở thành S nên một protected instance access phù hợp từ code của S có thể hợp lệ.

**Câu 5.** Nếu `C c = new S();` thì `c.protectedMethod()` có tự hợp lệ trong S không?

**Đáp án:** Không. Runtime object thuộc S không đổi compile-time type `C` của biểu thức `c`.

**Câu 6.** Nếu `Alpha extends C` và `Beta extends C` nhưng Beta không là subtype Alpha, code của Alpha ở package khác có được gọi `beta.protectedMethod()` không?

**Đáp án:** Không theo quy tắc receiver protected instance member được khai báo ở C, vì `Beta` không là Alpha/subtype Alpha.

**Câu 7.** Subclass ở package khác có thể dùng `super.protectedMethod()` không?

**Đáp án:** Có trong ngữ cảnh thích hợp; `super` cho phép chọn implementation superclass trên current object theo quy tắc Java. Không phải gọi trên một object superclass tùy ý.

**Câu 8.** Subclass constructor ở package khác có thể gọi `super(args)` tới protected superclass constructor không?

**Đáp án:** Có khi constructor accessible và quy tắc invocation thỏa mãn. Nhưng `new Superclass(args)` từ một method bất kỳ trong subclass không tự hợp lệ.

**Câu 9.** `S` override protected method của C thành public. Caller có biến `S s` và biến `C c = s`. Vì sao `s.method()` hợp lệ nhưng `c.method()` có thể bị từ chối?

**Đáp án:** `S.method()` đã được khai báo public trong S, còn qua compile-time type C, member được tìm từ C với mức protected và caller không có đường truy cập phù hợp.

**Câu 10.** `Peer` nằm cùng package với C, không extends C. Tại sao `Peer.inspect(C c)` có thể gọi protected instance method trên c?

**Đáp án:** Vì protected same-package access không có giới hạn receiver type của subclass khác package.

**Câu 11.** `this.protectedField` và `this.protectedMethod()` có cùng đặc trưng runtime không?

**Đáp án:** Chúng cùng cần hợp lệ về access, nhưng field access không virtual dispatch như overridable instance method. Một method override có thể chọn implementation theo runtime class.

**Câu 12.** Java module client đã `requires` module chứa C nhưng package của C không export. Subclass client có chắc dùng được public C không?

**Đáp án:** Không. Named module còn có quy tắc readability/export/type accessibility; protected access không bãi bỏ module boundary.

## 20. Checklist khi gặp lỗi `protected has access`

1. **Xác định nơi khai báo member:** nằm trong class C thuộc package nào?
2. **Xác định package của code gọi:** có thật sự **cùng package** với C không? Chú ý subpackage không tương đương.
3. **Nếu khác package:** code gọi có thuộc ngữ cảnh **subclass S của C** đủ điều kiện không?
4. **Với instance member:** biểu thức receiver có **compile-time type S hoặc subtype S** không?
5. **Kiểm tra `this` và `super`:** nếu cần dùng member trên current subclass object, nên gọi qua receiver đúng thay vì tham số Base tùy ý.
6. **Xem kiểu khai báo, không chỉ runtime type:** `C x = new S()` vẫn có compile-time type C.
7. **Nếu đang trong subclass khác package và muốn gọi qua C reference:** cân nhắc public API của C hoặc kiểu hóa lại bằng subclass sau khi kiểm tra runtime type hợp lệ.
8. **Nếu hai subclass khác nhánh:** không mặc nhiên cho quyền xem protected state trên object sibling.
9. **Nếu member static/constructor/nested type:** áp dụng đúng quy tắc riêng, không sao chép máy móc rule instance.
10. **Nếu method được override:** phân biệt visibility của declaration được chọn với dispatch đến implementation runtime.
11. **Nếu đang thiết kế API:** ưu tiên private state và protected methods có hợp đồng rõ, tránh protected mutable fields.
12. **Nếu code thuộc named modules:** kiểm tra readability, package exports và quyền truy cập kiểu ngoài member.
13. **Dùng `javac` để xác nhận:** thử một biểu thức sai tại một thời điểm, xem lỗi access/receiver và sửa đúng thiết kế thay vì cast tùy tiện.

**Ghi nhớ:** `protected` trong Java **mở quyền cho code cùng package** và **mở quyền có điều kiện cho subclass ở package khác**. Trong nhánh subclass khác package, với **protected instance field/method** truy cập qua receiver expression, kiểu tĩnh của receiver phải là **chính subclass S chứa ngữ cảnh truy cập hoặc subtype của S** theo quy tắc JLS. Vì vậy `this.member` hay `peerS.member` có thể hợp lệ, trong khi `baseC.member` lại không hợp lệ dù object runtime có thể thuộc S. Hiểu đúng *package*, *subclass context*, *receiver type* và *runtime dispatch* giúp sử dụng `protected` chính xác và thiết kế Java API dễ mở rộng mà không phá đóng gói.
