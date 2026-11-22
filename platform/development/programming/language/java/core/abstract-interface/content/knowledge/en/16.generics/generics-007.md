# Self-Referential Types with Comparable&lt;T&gt; and Fluent Style

## 1. F-bounded polymorphism

A type parameter can appear in its own bound, for example **T extends Comparable&lt;T&gt;** or **T extends Builder&lt;T&gt;**. This pattern is commonly called F-bounded polymorphism. It helps the compiler preserve concrete type information in comparison APIs or fluent call chains.

This is a compile-time type constraint, not a dedicated self type in Java, and it does not by itself guarantee that every subclass is designed correctly.

## 2. Comparable&lt;T&gt; preserves the type of the object being compared

~~~java
record Version(int major, int minor) implements Comparable<Version> {
    @Override
    public int compareTo(Version other) {
        int order = Integer.compare(major, other.major);
        if (order != 0) {
            return order;
        }
        return Integer.compare(minor, other.minor);
    }
}
~~~

When Version implements Comparable&lt;Version&gt;, the compareTo method accepts a Version. A negative value means the current object comes before the argument, 0 means they are equal in natural ordering, and a positive value means it comes after. There is no need to return exactly -1 or 1.

Use Integer.compare/Long.compare instead of direct subtraction, because subtraction can overflow. The compareTo ordering should have sign symmetry, transitivity, and consistency; Java recommends that natural ordering be consistent with equals, especially when using TreeSet or TreeMap.

A generic API often uses the bound **T extends Comparable<? super T>** to accept a type that can be compared with T or a suitable supertype of T.

## 3. Preserving subclass types in fluent APIs

If a method in the superclass returns the superclass type itself, a call chain can lose methods that exist only in the subclass:

~~~java
class BaseBuilder {
    BaseBuilder name(String value) {
        return this;
    }
}
~~~

If UserBuilder adds email(String), the call new UserBuilder().name("Ada").email("ada@example.com") does not compile after name(), because the expression has type BaseBuilder.

The self-referential pattern solves this problem:

~~~java
abstract class Builder<T extends Builder<T>> {
    public T name(String value) {
        return self();
    }

    protected abstract T self();
}
~~~

The subclass supplies its own type for T. The self() method allows the base class to return a value of the concrete type without needing an unchecked cast such as (T) this.

## 4. Runnable example

Save the code to **FluentBuilderDemo.java**:

~~~java
public class FluentBuilderDemo {
    abstract static class SelfBuilder<T extends SelfBuilder<T>> {
        private String name;

        public T name(String name) {
            this.name = name;
            return self();
        }

        protected abstract T self();

        protected String nameValue() {
            return name;
        }
    }

    static final class UserBuilder extends SelfBuilder<UserBuilder> {
        private String email;

        public UserBuilder email(String email) {
            this.email = email;
            return self();
        }

        @Override
        protected UserBuilder self() {
            return this;
        }

        User build() {
            return new User(nameValue(), email);
        }
    }

    record User(String name, String email) {}

    public static void main(String[] args) {
        User user = new UserBuilder()
                .name("Ada")
                .email("ada@example.com")
                .build();
        System.out.println(user);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac FluentBuilderDemo.java
java FluentBuilderDemo
~~~

Output:

~~~text
User[name=Ada, email=ada@example.com]
~~~

After name("Ada"), the expression type remains UserBuilder, so email() and then build() can be called. No cast is needed because self() returns UserBuilder.

## 5. Limitations and common pitfalls

- **An F-bound is not a strict self type:** a subclass can still declare an inappropriate relationship if the design allows it; keep the type argument consistent and restrict inheritance when needed.
- **Do not use unchecked casts arbitrarily:** (T) this can hide errors in the inheritance hierarchy. The abstract self() pattern forces the subclass to provide an explicit return type.
- **Do not confuse compareTo with equals:** they are two different contracts; clearly decide which fields participate in the ordering.
- **Do not compare numbers using subtraction:** use the standard compare methods to avoid overflow.
- **Do not add an F-bound just because an API has multiple classes:** use it when you genuinely need to preserve the concrete type in results or comparison contracts.

F-bounded polymorphism is suitable for Comparable, builders, and fluent APIs with multiple levels of inheritance. For regular class/interface bounds, see the article on type bounds; for bounds combined with &, see the article on intersection types.
