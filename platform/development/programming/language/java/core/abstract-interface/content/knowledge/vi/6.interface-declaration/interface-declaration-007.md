# Các kiểu thành viên được khai báo bên trong interface

## 1. Kiểu thành viên là gì?

Interface có thể chứa khai báo kiểu dữ liệu trực tiếp trong thân của nó. Các kiểu đó được gọi là **member types**. Java cho phép nested class, nested interface, enum, record (Java 16+) và annotation interface:

```java
interface Transport {
    interface Driver {
        void drive();
    }

    class Route {
        private final String name;

        Route(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    enum Mode {
        ROAD, RAIL
    }

    record Ticket(String code) {}

    @interface Audited {}
}
```

Tên đầy đủ của các kiểu trong ví dụ lần lượt là `Transport.Driver`, `Transport.Route`, `Transport.Mode`, `Transport.Ticket` và `Transport.Audited`. Chúng là kiểu, không phải field hoặc method của `Transport`.

## 2. Modifier ngầm định: public static

Mọi member type khai báo trực tiếp trong interface đều ngầm định `public static`, kể cả khi không viết hai từ khóa đó.

- `static` nghĩa là kiểu thành viên không cần một instance của interface bao ngoài. Không thể tạo instance của `Transport` vì đó là interface, và cũng không cần một instance như vậy để tạo `Transport.Route`.
- `public` là modifier của member type; nhưng nó không vượt qua quyền truy cập của kiểu bao ngoài. Nếu top-level interface bao ngoài là package-private, mã ngoài package vẫn không thể truy cập nó chỉ nhờ member type public.
- Không đặt `private` hoặc `protected` lên member type được khai báo trực tiếp trong interface.

Cách sử dụng:

```java
Transport.Route route = new Transport.Route("North");
Transport.Mode mode = Transport.Mode.RAIL;
Transport.Ticket ticket = new Transport.Ticket("T-1");
```

`Transport.Route` là static nested class và có constructor riêng. Nó không cần cú pháp `outer.new Route(...)`.

## 3. Ví dụ chạy được trên Java 17+

```java
interface Library {
    interface Identified {
        String id();
    }

    class Holder {
        private final String text;

        Holder(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    enum Status {
        DRAFT, PUBLISHED
    }

    record Book(String id, String title) implements Identified {}
}

public class Main {
    public static void main(String[] args) {
        Library.Holder holder = new Library.Holder("Notes");
        Library.Book book = new Library.Book("B01", "Java");
        Library.Identified identified = book;
        System.out.println(holder.text());
        System.out.println(identified.id() + " - " + book.title());
        System.out.println(Library.Status.PUBLISHED);
    }
}
```

Kết quả:

```text
Notes
B01 - Java
PUBLISHED
```

`Library.Book` là record nên tự cung cấp accessor `id()` và `title()`. Nó triển khai `Library.Identified` một cách tường minh; việc khai báo bên trong `Library` không tự tạo quan hệ `implements` với interface bao ngoài.

## 4. Phân biệt kiểu thành viên với field và method

```java
interface Sensor {
    int MAX_RETRIES = 3;  // Field: public static final
    int read();           // Method: public abstract

    default boolean ready() {
        return read() >= 0;
    }

    static String category() {
        return "sensor";
    }

    record Reading(int value) {} // Member type: public static
}
```

`MAX_RETRIES` là field hằng; `read`, `ready` và `category` là method; `Reading` là kiểu. Đừng suy ra class thành viên thông thường là final hoặc immutable chỉ vì nó nằm trong interface. Chẳng hạn record là final theo quy tắc của record, còn nested class bình thường có thể có state và method thay đổi.

## 5. Vị trí khai báo không tạo quan hệ kiểu

Một nested class không tự động triển khai interface bao ngoài:

```java
interface Task {
    void execute();

    class Config {}
    class Worker implements Task {
        @Override
        public void execute() {
            System.out.println("working");
        }
    }
}
```

`Task.Config` không phải là `Task`. `Task.Worker` mới là `Task` vì khai báo `implements Task` rõ ràng và cung cấp `execute()`. Tương tự, nested interface chỉ kế thừa interface bao ngoài khi nó khai báo `extends`.

## 6. Khi nào nên lồng một kiểu?

Member type phù hợp khi kiểu đó gắn chặt về ý nghĩa với API bao ngoài, ví dụ `Parser.Result`, `Connection.State` hoặc `EventBus.Listener`. Cách gọi `Outer.Member` giúp người đọc nhận ra nhóm khái niệm liên quan.

Nếu kiểu được dùng độc lập bởi nhiều API hoặc có trách nhiệm riêng lớn, hãy cân nhắc top-level type để tăng khả năng tái sử dụng. Luôn kiểm tra riêng quy tắc truy cập, `extends` và `implements`; vị trí lồng nhau chỉ tổ chức tên và phạm vi, không tự tạo quan hệ kế thừa.