# Giới hạn gọi super qua interface trực tiếp trong Java

Cú pháp `I.super.method()` có những giới hạn về quan hệ kế thừa. Tên interface trước `.super` phải là superinterface trực tiếp phù hợp của **chính class hoặc interface đang chứa lời gọi**, và lời gọi không được dùng để bỏ qua một nhánh interface cụ thể hơn.

## 1. Trực tiếp và gián tiếp không giống nhau

```java
interface Base {
    default String label() {
        return "Base";
    }
}

interface Extended extends Base {
}

final class Item implements Extended {
    @Override
    public String label() {
        return Extended.super.label() + " -> Item";
    }
}
```

`Extended.super.label()` hợp lệ vì `Extended` được liệt kê trực tiếp trong `implements` của `Item`. Dù phần thân ban đầu được khai báo trong `Base`, `Extended` kế thừa default đó và là qualifier thích hợp tại vị trí gọi.

Ngược lại, `Base.super.label()` bên trong `Item` không hợp lệ: `Base` chỉ là superinterface gián tiếp. Không thể dùng qualified super call để nhảy tùy ý đến tổ tiên xa hơn.

## 2. Không được bỏ qua interface con cụ thể hơn

Xét `A` có default method và `B extends A` override phương thức đó. Nếu class trực tiếp khai báo `implements A, B`, Java không cho gọi `A.super.method()` để bỏ qua implementation cụ thể hơn từ `B`.

```java
interface A {
    default String name() { return "A"; }
}

interface B extends A {
    @Override
    default String name() { return "B"; }
}

class C implements A, B {
    @Override
    public String name() {
        return B.super.name();
    }
}
```

`B.super.name()` chọn nhánh chuyên biệt hơn. Đổi thành `A.super.name()` là lỗi biên dịch vì `B` cũng là superinterface trực tiếp của `C` và là subtype của `A`. Liệt kê cả cha và con trong `implements` không tạo quyền bỏ qua override của con.

## 3. Tôn trọng quyết định ở tầng trung gian

```java
interface Root {
    default String format() {
        return "Root";
    }
}

interface Middle extends Root {
    @Override
    default String format() {
        return "Middle(" + Root.super.format() + ")";
    }
}

class Bottom implements Middle {
    @Override
    public String format() {
        return Middle.super.format() + " -> Bottom";
    }
}
```

Chuỗi gọi hợp lệ là `Middle` gọi `Root.super.format()` tại nơi `Root` trực tiếp được kế thừa; `Bottom` gọi `Middle.super.format()`. Kết quả `new Bottom().format()` là `Middle(Root) -> Bottom`. Không có cú pháp tổng quát để nhảy qua nhiều tầng và cưỡng ép chạy một thân cũ; mỗi tầng cần tôn trọng quan hệ kế thừa của chính nó.

## 4. Những trường hợp không thể dùng qualified super

- **Không có thân default:** một phương thức abstract không có implementation để gọi.
- **Static hoặc private:** static method được gọi bằng tên interface; private helper chỉ được gọi từ nơi có quyền truy cập theo quy tắc Java.
- **Static context:** default method là instance method nên qualified super call không hợp lệ trong phương thức static.
- **Chỉ được kế thừa qua superclass:** nếu `Parent implements Labelled` và `Child extends Parent`, `Labelled` không tự trở thành superinterface trực tiếp của `Child`. Child có thể dùng phương thức kế thừa theo cách gọi instance bình thường hoặc qua `super` khi thích hợp.
- **Có nhánh trực tiếp cụ thể hơn:** không được chọn qualifier tổ tiên để bỏ qua override của superinterface con.

| Tình huống | Cách xử lý |
| --- | --- |
| `C implements B` và `B extends A` | Xem xét `B.super.m()`, không gọi `A.super.m()` từ C. |
| `C implements A, B` và `B extends A` | Tôn trọng nhánh cụ thể hơn `B`. |
| `C implements Left, Right`, hai default độc lập xung đột | Override trong C và chọn rõ `Left.super.m()`/`Right.super.m()` nếu cần. |
| Phương thức đích là abstract/static/private | Không gọi bằng qualified super; dùng cơ chế phù hợp với loại phương thức. |

**Ghi nhớ:** không chỉ tên interface được ghi trong `implements` quan trọng; cấu trúc kế thừa và các override cũng quyết định lời gọi có hợp lệ hay không. Nếu cần tái sử dụng hành vi qua nhiều tầng, hãy để từng interface trung gian quyết định cách phơi bày hoặc mở rộng hành vi của tổ tiên.